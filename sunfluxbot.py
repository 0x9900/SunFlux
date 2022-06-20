#!/usr/bin/env python3.9
#
#

import json
import logging
import os
import pickle
import subprocess
import time
import urllib.parse
import urllib.request

from datetime import datetime

from telegram import (
  InlineKeyboardButton,
  InlineKeyboardMarkup,
  Update,
)
from telegram.ext import (
  CallbackContext,
  CallbackQueryHandler,
  CommandHandler,
  ConversationHandler,
  Filters,
  MessageHandler,
  Updater,
)

from config import Config
from showdxcc import CONTINENTS

logging.basicConfig(
  format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s',
  datefmt='%H:%M:%S',
  level=logging.getLevelName(os.getenv('LEVEL', 'INFO'))
)
logger = logging.getLogger(__name__)

NOAA_URL = 'https://services.swpc.noaa.gov/'
ALERT_SHORT = NOAA_URL + 'text/wwv.txt'
ALERT_URL = NOAA_URL + 'products/alerts.json'

IMG_SOURCE = {
  'ai':    'images/station-a-index.png',
  'geost': 'images/geospace/geospace_7_day.png',
  'ki':    'images/station-k-index.png',
  'swx':   'images/swx-overview-large.gif',
  'tec':   'images/animations/ctipe/tec/latest.png',
  'swo':   'images/swx-overview-large.gif',
  'warn':  'images/notifications-timeline.png',
}
IMG_CACHE_TIME = (3600 * 4)

class SunRecord:
  """Datastructure holding the sun Flux information"""
  __slots__ = ("date", "data")

  def __init__(self, args):
    self.date = datetime.strptime('{} {} {}'.format(*args[0:3]), "%Y %b %d")
    self.data = {}
    self.data['flux'] = int(args[3])
    self.data['a_index'] = int(args[4])
    self.data['kp_index'] = int(args[5])

  def __repr__(self):
    info = ' '.join('%s: %s' % (k, v) for k, v  in self.data.items())
    return '{} [{}]'.format(self.__class__, info)

  def __str__(self):
    return "{0.date} {0.flux} {0.a_index} {0.kp_index}".format(self)

  @property
  def flux(self):
    return self.data['flux']

  @property
  def a_index(self):
    return self.data['a_index']

  @property
  def kp_index(self):
    return self.data['kp_index']

def get_alert(cache_dir):
  """NOAA space weather alerts"""
  cachefile = os.path.join(cache_dir, 'alerts.pkl')
  now = time.time()
  try:
    cache_st = os.stat(cachefile)
    if now - cache_st.st_atime > 3600:
      raise FileNotFoundError
  except (FileNotFoundError, EOFError):
    alerts = []
    alerts.append(download_alert())
    alerts.append('=' * 5)
    alerts.append(download_short_alert())
    alerts.append('=' * 5)
    alerts.append('For more information on the sun activity:')
    alerts.append('https://www.swpc.noaa.gov/communities/space-weather-enthusiasts')
    alert = '\n'.join(alerts)
    writecache(cachefile, alert)
    return alert

  alert = readcache(cachefile)
  return alert

def download_short_alert():
  try:
    req = urllib.request.urlopen(ALERT_SHORT)
    webdata = req.read()
    encoding = req.info().get_content_charset('utf-8')
    webdata = webdata.decode(encoding)
  except urllib.request.URLError as err:
    logging.error('Connection error: %s we will try later', err)
    return ""

  lines = []
  if req.status == 200:
    for line in webdata.splitlines():
      line = line.strip()
      if not line or line.startswith(':') or line.startswith('#'):
        continue
      if (line.startswith('Solar-terrestrial indices for') or
          line.startswith('No space weather storms')):
        continue
      lines.append(line)

  return '\n'.join(lines)

def download_alert():
  try:
    req = urllib.request.urlopen(ALERT_URL)
    webdata = req.read()
    encoding = req.info().get_content_charset('utf-8')
    webdata = webdata.decode(encoding)
  except urllib.request.URLError as err:
    logging.error('Connection error: %s we will try later', err)
    return ""

  if req.status != 200:
    return ""

  data = json.loads(webdata)
  alerts = dict()
  for record  in data:
    issue_date = datetime.strptime(record['issue_datetime'],
                                   '%Y-%m-%d %H:%M:%S.%f')
    alerts[issue_date] = record['message']

    if not alerts:
      return ""

    alert = alerts[sorted(alerts, reverse=True)[0]]
    text_alert = []
    for line in alert.splitlines():
      line = line.rstrip()
      if (not line or line.startswith('NOAA Space Weather Scale desc') or
          line.endswith('explanation')):
        continue
      text_alert.append(line)
    return '\n'.join(text_alert)


def noaa_download(image):
  config = Config()
  cache_dir = config.get('sunfluxbot.cache_dir', '/tmp')
  if image not in IMG_SOURCE:
    logging.error(f"Image {image} not available")
    return

  url = NOAA_URL + IMG_SOURCE[image]
  full_path = os.path.join(cache_dir, image +'.png')
  now = time.time()

  try:
    filest = os.stat(full_path)
    if now - filest.st_atime > IMG_CACHE_TIME:
      raise FileNotFoundError
  except FileNotFoundError:
    urllib.request.urlretrieve(url, full_path)
  return full_path

def readcache(cachefile):
  """Read data from the cache"""
  try:
    with open(cachefile, 'rb') as fd_cache:
      data = pickle.load(fd_cache)
  except (FileNotFoundError, EOFError):
    data = None
  return data

def writecache(cachefile, data):
  """Write data into the cachefile"""
  with open(cachefile, 'wb') as fd_cache:
    pickle.dump(data, fd_cache)

def error_callback(update, context):
  logger.warning('error_callback - Update "%s" error "%s"',
                 update, context.error)

def help_command(update: Update, context: CallbackContext):
  help = [
    "*Use the following commands:*",
    "> /aindex: A Index",
    "> /alerts: NOAA Alerts",
    "> /dxcc: Show dxcc contacts",
    "> /flux: 10cm Flux",
    "> /geost: Geo-Space Time line",
    "> /kpindex: K Index",
    "> /legend: Index information",
    "> /ssn: Sun Spots",
    "> /swx: Solar indices overview",
    "> /tec: Total Electron Content",
    "> /warning: Warning time lines",
    "\n*Propagation information:*",
    "> _For best radio propagation_",
    "> `Flux >= 80, KPIndex >= 3, AIndex >= 10`",
    "",
    "\n_For more information or contact see /credits_"
  ]
  update.message.reply_text("\n".join(help), parse_mode='Markdown')
  user = update.message.chat.username or "Stranger"
  chat_id = update.message.chat.id
  logger.info(f"Command /help by {user}:{chat_id}")
  return ConversationHandler.END

def send_credits(update: Update, context: CallbackContext):
  credits = [
    "The solar data courtesy of NOAA",
    "> https://swpc.noaa.gov",
    "The DXCC heatmap data courtesy of the following clusters:",
    "> dx.maritimecontestclub.ca",
    "> dxc.ai9t.com",
    "> dxc.nc7j.com",
    "> n8dxe.dxengineering.com",
    "> w3lpl.net",
    "The SunFluxBot was developed by Fred (W6BSD)",
    "To report a bug send a message at https://t.me/w6bsd",
  ]
  update.message.reply_text("\n".join(credits), parse_mode='Markdown')
  return ConversationHandler.END

def send_flux(update: Update, context: CallbackContext):
  config = Config()
  cache_dir = config.get('sunfluxbot.cache_dir', '/tmp')
  now = time.time()
  image = os.path.join(cache_dir, 'flux.png')
  chat_id = update.message.chat_id
  today = datetime.now().strftime('%a %b %d %Y')

  try:
    img_st = os.stat(image)
    if now - img_st.st_atime > IMG_CACHE_TIME:
      raise FileNotFoundError
  except (FileNotFoundError, EOFError):
    cmd = os.path.join(os.getcwd(), "fluxgraph.py")
    status = subprocess.call([cmd], shell=False)
    logging.info(f'Call {cmd} returned {status}')
    if status:
      logging.error('Error generating the flux graph')
      context.bot.send_message(chat_id, (
        'The flux graph is not available at the moment\n'
        'Please come back latter.'))
      return ConversationHandler.END

  context.bot.send_photo(chat_id=chat_id, photo=open(image, 'rb'),
                         caption="10cm flux for: {}".format(today),
                         filename=os.path.basename(image), timeout=100)
  return ConversationHandler.END

def send_ssn(update: Update, context: CallbackContext):
  config = Config()
  cache_dir = config.get('ssn.cache_dir', '/tmp')
  now = time.time()
  image = os.path.join(cache_dir, 'ssn.png')
  chat_id = update.message.chat_id
  today = datetime.now().strftime('%a %b %d %Y')

  try:
    img_st = os.stat(image)
    if now - img_st.st_atime > IMG_CACHE_TIME:
      raise FileNotFoundError
  except (FileNotFoundError, EOFError):
    cmd = os.path.join(os.getcwd(), "ssngraph.py")
    status = subprocess.call([cmd], shell=False)
    logging.info(f'Call {cmd} returned {status}')
    if status:
      logging.error('Error generating the sun spot graph')
      context.bot.send_message(chat_id, (
        'The Sun Spot graph is not available at the moment\n'
        'Please come back latter.'))
      return ConversationHandler.END

  context.bot.send_photo(
    chat_id=chat_id, photo=open(image, 'rb'),
    caption="Estimated International Sunspot Number: {}".format(today),
    filename=os.path.basename(image), timeout=100)
  return ConversationHandler.END


def send_tec(update: Update, context: CallbackContext):
  try:
    filename = noaa_download('tec')
  except Exception as exp:
    logger.error(exp)
    update.message.reply_text(f'Error: {exp}')
    return ConversationHandler.END

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='Total Electron Content',
                         filename=os.path.basename(filename), timeout=100)
  return ConversationHandler.END

def send_geost(update: Update, context: CallbackContext):
  try:
    filename = noaa_download('geost')
  except Exception as exp:
    logger.error(exp)
    update.message.reply_text(f'Error: {exp}')
    return ConversationHandler.END

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='Geospace timeline',
                         filename=os.path.basename(filename), timeout=100)
  return ConversationHandler.END

def send_aindex(update: Update, context: CallbackContext):
  try:
    filename = noaa_download('ai')
  except Exception as exp:
    logger.error(exp)
    update.message.reply_text(f'Error: {exp}')
    return ConversationHandler.END

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='A Index',
                         filename=os.path.basename(filename), timeout=100)
  return ConversationHandler.END

def send_kpindex(update: Update, context: CallbackContext):
  config = Config()
  cache_dir = config.get('sunfluxbot.cache_dir', '/tmp')
  now = time.time()
  image = os.path.join(cache_dir, 'kpindex.png')
  chat_id = update.message.chat_id
  today = datetime.now().strftime('%a %b %d %Y')
  try:
    img_st = os.stat(image)
    if now - img_st.st_atime > IMG_CACHE_TIME:
      raise FileNotFoundError
  except (FileNotFoundError, EOFError):
    cmd = os.path.join(os.getcwd(), "kpindexgraph.py")
    status = subprocess.call([cmd], shell=False)
    logging.info(f'Call {cmd} returned {status}')
    if status:
      logging.error('Error generating the kpindex graph')
      context.bot.send_message(chat_id, (
        'The kpindex graph is not available at the moment\n'
        'Please come back latter.'))
      return ConversationHandler.END

  context.bot.send_photo(chat_id=chat_id, photo=open(image, 'rb'),
                         caption="Planetary KPIndex for: {}".format(today),
                         filename=os.path.basename(image), timeout=100)
  return ConversationHandler.END

def send_swx(update: Update, context: CallbackContext):
  try:
    filename = noaa_download('swx')
  except Exception as exp:
    logger.error(exp)
    update.message.reply_text(f'Error: {exp}')
    return

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='Space weather indices',
                         filename=os.path.basename(filename), timeout=100)

def send_swo(update: Update, context: CallbackContext):
  try:
    filename = noaa_download('swo')
  except Exception as exp:
    logger.error(exp)
    update.message.reply_text(f'Error: {exp}')
    return ConversationHandler.END

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='Space weather indices overview',
                         filename=os.path.basename(filename), timeout=100)
  return ConversationHandler.END

def send_warn(update: Update, context: CallbackContext):
  try:
    filename = noaa_download('warn')
  except Exception as exp:
    logger.error(exp)
    update.message.reply_text(f'Error: {exp}')
    return ConversationHandler.END

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='Space weather warning timelines',
                         filename=os.path.basename(filename), timeout=100)
  return ConversationHandler.END

def send_alerts(update: Update, context: CallbackContext):
  config = Config()
  cache_dir = config.get('sunfluxbot.cache_dir', '/tmp')
  alert = get_alert(cache_dir)
  update.message.reply_text(alert)
  return ConversationHandler.END

def dxcc_handler(update: Update, context: CallbackContext):
  keyboard = []
  for key in CONTINENTS:
    keyboard.append(InlineKeyboardButton(key, callback_data=key))
  reply_markup = InlineKeyboardMarkup([keyboard])
  update.message.reply_text('What is your continent?', reply_markup=reply_markup)

def send_dxcc(update: Update, context: CallbackContext):
  config = Config()
  cache_dir = config.get('sunfluxbot.cache_dir', '/tmp')
  query = update.callback_query
  chat_id = query.message.chat.id
  user = query.message.chat.username or str(chat_id)
  image = f'/tmp/dxcc-{query.data}-{user}.png'
  now = time.time()
  today = datetime.now().strftime('%a %b %d %Y at %H:%M')

  try:
    img_st = os.stat(image)
    if now - img_st.st_atime > 300:
      raise FileNotFoundError
  except (FileNotFoundError, EOFError):
    cmd = os.path.join(os.getcwd(), "showdxcc.py")
    status = subprocess.call([cmd, query.data, image], shell=False)
    logging.info(f'Call "{cmd} {query.data} {image}" returned {status}')
    if status:
      logging.error('Error generating the dxcc graph')
      context.bot.send_message(chat_id, (
        'The dxcc graph is not available at the moment\n'
        'Please come back latter.'))
      return ConversationHandler.END
  else:
    logging.info(f'Send {image} from cache')

  context.bot.send_photo(chat_id=chat_id, photo=open(image, 'rb'),
                         caption=f"DX activity for: {today}",
                         filename=os.path.basename(image), timeout=100)
  return ConversationHandler.END

def start(update: Update, context: CallbackContext):
  botname = update.message.bot.first_name
  user = update.message.chat.username or "Stranger"
  chat_id = update.message.chat.id
  lines = [f"Welcome {user} to the {botname} developped by W6BSD",
           "This bot is experimental any feedback is welcome",
           "Use '/help' to see the list of commands"]
  update.message.reply_text('\n'.join(lines))
  logger.info(f"Command /start by {user}:{chat_id}")
  return ConversationHandler.END

def text_handler(update: Update, context: CallbackContext):
  user = update.message.chat.username or "Stranger"
  message = update.message.text
  logging.info(f">>> {user} sent the message \"{message}\"")
  if not message.startswith('/'):
    update.message.reply_text(
      "Thank you for your words of encouragments, but I am a robot and not "
      "capable of having a conversation with you.\n"
      "If you want to know all my capabilities use the /help command.\n"
      "In the mean time let me call help for you.\n73",
      reply_to_message_id=update.message.message_id)
  else:
    update.message.reply_text(f'Command "{message.strip("/")}" unknown')

  help_command(update, context)
  return ConversationHandler.END

def send_legend(update: Update, context: CallbackContext):
  legend = (
    "/Aindex *LOW = GOOD*",
    "- 1 to 6 is Best",
    "- 7 to 9 is Ok",
    "- >11 is Bad",
    "_A lower A-Index suggests better propagation._",
    "",
    "/flux *HIGH = GOOD*",
    "- 70 is Bad",
    "- 80 is Good",
    "- 90 is Better",
    "- >100 is Best",
    "_Total radio emissions from the sun at 2800MHz._",
    "",
    "/Kpindex *LOW = Good*",
    "- 0..1 is Best",
    "- 2 is Ok",
    "- 3 or Bad",
    "- 5 very Bad",
    "_Kp Index is the planet's average over the last 3 hours._"
  )
  update.message.reply_text("\n".join(legend), parse_mode='Markdown')
  return ConversationHandler.END


def main():
  config = Config()
  updater = Updater(config['sunfluxbot.token'])
  updater.bot.logger.level = logging.INFO
  updater.dispatcher.add_handler(CommandHandler('ai', send_aindex))
  updater.dispatcher.add_handler(CommandHandler('aindex', send_aindex))
  updater.dispatcher.add_handler(CommandHandler('alert', send_alerts))
  updater.dispatcher.add_handler(CommandHandler('alerts', send_alerts))
  updater.dispatcher.add_handler(CommandHandler('credits', send_credits))
  updater.dispatcher.add_handler(CommandHandler('dxcc', dxcc_handler))
  updater.dispatcher.add_handler(CommandHandler('flux', send_flux))
  updater.dispatcher.add_handler(CommandHandler('geost', send_geost))
  updater.dispatcher.add_handler(CommandHandler('help', help_command))
  updater.dispatcher.add_handler(CommandHandler('kpi', send_kpindex))
  updater.dispatcher.add_handler(CommandHandler('kpindex', send_kpindex))
  updater.dispatcher.add_handler(CommandHandler('ssn', send_ssn))
  updater.dispatcher.add_handler(CommandHandler('start', start))
  updater.dispatcher.add_handler(CommandHandler('swx', send_swx))
  updater.dispatcher.add_handler(CommandHandler('tec', send_tec))
  updater.dispatcher.add_handler(CommandHandler('warning', send_warn))
  updater.dispatcher.add_handler(CommandHandler('legend', send_legend))
  updater.dispatcher.add_handler(MessageHandler(Filters.text, text_handler))
  updater.dispatcher.add_handler(CallbackQueryHandler(send_dxcc))
  updater.dispatcher.add_error_handler(error_callback)

  updater.start_polling()
  updater.idle()


if __name__ == "__main__":
  main()
