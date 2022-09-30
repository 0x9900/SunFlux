#!/usr/bin/env python3.9
#
#

import json
import logging
import os
import pickle
import subprocess
import sys
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
  datefmt='%Y-%m-%d %H:%M:%S',
  level=logging.getLevelName(os.getenv('LEVEL', 'INFO'))
)
logger = logging.getLogger(__name__)

NOAA_URL = 'https://services.swpc.noaa.gov/'
ALERT_SHORT = NOAA_URL + 'text/wwv.txt'
ALERT_URL = NOAA_URL + 'products/alerts.json'

IMG_SOURCE = {
  'ai':    'images/station-a-index.png',
  'drap':  'images/animations/d-rap/global_f05/d-rap/latest.png',
  'geost': 'images/geospace/geospace_7_day.png',
  'ki':    'images/station-k-index.png',
  'muf':   'experimental/images/animations/ctipe/muf/latest.png',
  'swo':   'images/swx-overview-large.gif',
  'swx':   'images/swx-overview-large.gif',
  'warn':  'images/notifications-timeline.png',
}
IMG_CACHE_TIME = (3600 * 2)

class SunRecord:
  """Datastructure holding the sun Flux information"""
  __slots__ = ("date", "data")

  def __init__(self, args):
    self.date = datetime.strptime(f'{args[0]} {args[1]} {args[2]}', "%Y %b %d")
    self.data = {}
    self.data['flux'] = int(args[3])
    self.data['a_index'] = int(args[4])
    self.data['kp_index'] = int(args[5])

  def __repr__(self):
    info = ' '.join(f"{k}: {v}" for k, v  in self.data.items())
    return f'{self.__class__} [{info}]'

  def __str__(self):
    return f"{self.date} {self.flux} {self.a_index} {self.kp_index}"

  @property
  def flux(self):
    return self.data['flux']

  @property
  def a_index(self):
    return self.data['a_index']

  @property
  def kp_index(self):
    return self.data['kp_index']

def urlretrieve(url, path):
  try:
    path, _ = urllib.request.urlretrieve(url, path)
  except urllib.request.URLError as err:
    logger.warning(err)
    return None
  return path

def get_alert(cache_dir):
  """NOAA space weather alerts"""
  cachefile = os.path.join(cache_dir, 'alerts.pkl')
  now = time.time()
  try:
    cache_st = os.stat(cachefile)
    if now - cache_st.st_mtime > 3600:
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
    logger.error('Connection error: %s we will try later', err)
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
    logger.error('Connection error: %s we will try later', err)
    return ""

  if req.status != 200:
    return ""

  data = json.loads(webdata)
  alerts = {}
  for record  in data:
    issue_date = datetime.strptime(
      record['issue_datetime'], '%Y-%m-%d %H:%M:%S.%f'
    )
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

def noaa_download(image, cache_time=IMG_CACHE_TIME):
  config = Config()
  cache_dir = config.get('sunfluxbot.cache_dir', '/tmp')
  if image not in IMG_SOURCE:
    logger.error("Image %s not available", image)
    return None

  url = NOAA_URL + IMG_SOURCE[image]
  full_path = os.path.join(cache_dir, image +'.png')
  now = time.time()

  try:
    filest = os.stat(full_path)
    if now - filest.st_mtime > cache_time:
      raise FileNotFoundError
  except FileNotFoundError:
    full_path = urlretrieve(url, full_path)
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

def help_command(update: Update, _context: CallbackContext):
  _help = [
    "*Use the following commands:*",
    "> /aindex - A Index",
    "> /alerts - NOAA Alerts",
    "> /drap - D Layer Absorption Prediction",
    "> /dxcc - Show dxcc contacts",
    "> /eisn - Estimated International Sunspot Number",
    "> /flux - 10cm Flux",
    "> /geost - Geo-Space Time line",
    "> /kpindex - K Index",
    "> /legend - Index information",
    "> /muf - Maximum Usable Frequency",
    "> /outlook - 27 day Solar Predictions",
    "> /ssn - Sun Spots",
    "> /swx - Solar indices overview",
    "> /warning - Warning time lines",
    "",
    "\n_For more information or contact see /credits_",
    "More solar activity graphs at https://bsdworld.org/",
  ]
  update.message.reply_text("\n".join(_help), parse_mode='Markdown')
  user = update.message.chat.username or "Stranger"
  chat_id = update.message.chat.id
  logger.info("Command /help by %s:%d", user, chat_id)
  return ConversationHandler.END

def send_credits(update: Update, _context: CallbackContext):
  _credits = [
    "The solar data courtesy of NOAA",
    "> https://swpc.noaa.gov",
    "The DXCC heatmap data courtesy of the following clusters:",
    "> dx.maritimecontestclub.ca",
    "> dxc.ai9t.com",
    "> dxc.nc7j.com",
    "> n8dxe.dxengineering.com",
    "> w3lpl.net",
    "More solar information at:",
    "https://bsdworld.org",
    "The SunFluxBot (beta) is developed by Fred (W6BSD)",
    "To send suggestions or to report a bug send a message at https://t.me/w6bsd",
  ]
  update.message.reply_text("\n".join(_credits), parse_mode='Markdown')
  return ConversationHandler.END

def send_outlook(update: Update, context: CallbackContext):
  config = Config()
  cache_dir = config.get('sunfluxbot.cache_dir', '/tmp')
  now = time.time()
  image = os.path.join(cache_dir, 'outlook.png')
  chat_id = update.message.chat_id

  try:
    img_st = os.stat(image)
    if now - img_st.st_mtime > IMG_CACHE_TIME:
      raise FileNotFoundError
  except (FileNotFoundError, EOFError):
    cmd = os.path.join(sys.path[0], "outlookgraph")
    status = subprocess.call([cmd], shell=False)
    logger.info('Call %s returned %d', cmd, status)
    if status:
      logger.error('Error generating the outlook graph')
      context.bot.send_message(chat_id, (
        'The outlook graph is not available at the moment\n'
        'Please come back latter.'))
      return ConversationHandler.END

  context.bot.send_photo(chat_id=chat_id, photo=open(image, 'rb'),
                         caption="27 day Solar Predictions",
                         filename=os.path.basename(image), timeout=100)
  user = update.message.chat.username or "Stranger"
  logger.info("Command /outlook by %s:%d", user, chat_id)
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
    if now - img_st.st_mtime > IMG_CACHE_TIME:
      raise FileNotFoundError
  except (FileNotFoundError, EOFError):
    cmd = os.path.join(sys.path[0], "fluxgraph")
    status = subprocess.call([cmd], shell=False)
    logger.info('Call %s returned %d', cmd, status)
    if status:
      logger.error('Error generating the flux graph')
      context.bot.send_message(chat_id, (
        'The flux graph is not available at the moment\n'
        'Please come back latter.'))
      return ConversationHandler.END

  context.bot.send_photo(chat_id=chat_id, photo=open(image, 'rb'),
                         caption=f"10cm flux for: {today}",
                         filename=os.path.basename(image), timeout=100)
  user = update.message.chat.username or "Stranger"
  logger.info("Command /flux by %s:%d", user, chat_id)
  return ConversationHandler.END

def send_ssn(update: Update, context: CallbackContext):
  config = Config()
  cache_dir = config.get('sunfluxbot.cache_dir', '/tmp')
  now = time.time()
  image = os.path.join(cache_dir, 'ssn.png')
  chat_id = update.message.chat_id
  today = datetime.now().strftime('%a %b %d %Y')

  try:
    img_st = os.stat(image)
    if now - img_st.st_mtime > IMG_CACHE_TIME:
      raise FileNotFoundError
  except (FileNotFoundError, EOFError):
    cmd = os.path.join(sys.path[0], "ssngraph")
    status = subprocess.call([cmd], shell=False)
    logger.info('Call %s returned %d', cmd, status)
    if status:
      logger.error('Error generating the sun spot graph')
      context.bot.send_message(chat_id, (
        'The Sun Spot graph is not available at the moment\n'
        'Please come back latter.'))
      return ConversationHandler.END

  context.bot.send_photo(
    chat_id=chat_id, photo=open(image, 'rb'),
    caption=f"Estimated International Sunspot Number: {today}",
    filename=os.path.basename(image), timeout=100)

  user = update.message.chat.username or "Stranger"
  logger.info("Command /ssn by %s:%d", user, chat_id)
  return ConversationHandler.END

def send_eisn(update: Update, context: CallbackContext):
  config = Config()
  cache_dir = config.get('sunfluxbot.cache_dir', '/tmp')
  now = time.time()
  image = os.path.join(cache_dir, 'eisn.png')
  chat_id = update.message.chat_id
  today = datetime.now().strftime('%a %b %d %Y')

  try:
    img_st = os.stat(image)
    if now - img_st.st_mtime > IMG_CACHE_TIME:
      raise FileNotFoundError
  except (FileNotFoundError, EOFError):
    cmd = os.path.join(sys.path[0], "eisngraph")
    status = subprocess.call([cmd], shell=False)
    logger.info('Call %s returned %d', cmd, status)
    if status:
      logger.error('Error generating the sun spot prediction graph')
      context.bot.send_message(chat_id, (
        'The Sun Spot Preditions graph is not available at the moment\n'
        'Please come back latter.'))
      return ConversationHandler.END

  context.bot.send_photo(
    chat_id=chat_id, photo=open(image, 'rb'),
    caption=f"Estimated International Sunspot Number: {today}",
    filename=os.path.basename(image), timeout=100)

  user = update.message.chat.username or "Stranger"
  logger.info("Command /eisn by %s:%d", user, chat_id)
  return ConversationHandler.END

def send_drap(update: Update, context: CallbackContext):
  filename = noaa_download('drap')
  if not filename:
    update.message.reply_text('The DRAP image cannot be displayed at the moment')
    return ConversationHandler.END

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='D Layer Absorption Prediction',
                         filename=os.path.basename(filename), timeout=100)

  user = update.message.chat.username or "Stranger"
  logger.info("Command /drap by %s:%d", user, chat_id)
  return ConversationHandler.END

def send_muf(update: Update, context: CallbackContext):
  filename = noaa_download('muf', cache_time=900)
  if not filename:
    update.message.reply_text('The MUF image cannot be displayed at the moment')
    return ConversationHandler.END

  today = datetime.now().strftime('%a %b %d %Y at %H:%M')
  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption=f'Maximum Usable Frequency for: {today}',
                         filename=os.path.basename(filename), timeout=100)

  user = update.message.chat.username or "Stranger"
  logger.info("Command /muf by %s:%d", user, chat_id)
  return ConversationHandler.END

def send_geost(update: Update, context: CallbackContext):
  filename = noaa_download('geost')
  if not filename:
    update.message.reply_text('The geost image cannot be displayed at the moment')
    return ConversationHandler.END

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='Geospace timeline',
                         filename=os.path.basename(filename), timeout=100)

  user = update.message.chat.username or "Stranger"
  logger.info("Command /geost by %s:%d", user, chat_id)
  return ConversationHandler.END

def send_aindex(update: Update, context: CallbackContext):
  config = Config()
  cache_dir = config.get('sunfluxbot.cache_dir', '/tmp')
  now = time.time()
  image = os.path.join(cache_dir, 'aindex.png')
  chat_id = update.message.chat_id
  today = datetime.now().strftime('%a %b %d %Y')
  try:
    img_st = os.stat(image)
    if now - img_st.st_mtime > IMG_CACHE_TIME:
      raise FileNotFoundError
  except (FileNotFoundError, EOFError):
    cmd = os.path.join(sys.path[0], "aindex")
    status = subprocess.call([cmd], shell=False)
    logger.info('Call %s returned %d', cmd, status)
    if status:
      logger.error('Error generating the aindex graph')
      context.bot.send_message(chat_id, (
        'The aindex graph is not available at the moment\n'
        'Please come back latter.'))
      return ConversationHandler.END

  context.bot.send_photo(chat_id=chat_id, photo=open(image, 'rb'),
                         caption=f"A-Index for: {today}",
                         filename=os.path.basename(image), timeout=100)

  user = update.message.chat.username or "Stranger"
  logger.info("Command /aindex by %s:%d", user, chat_id)
  return ConversationHandler.END


def send_kpindex(update: Update, context: CallbackContext):
  config = Config()
  cache_dir = config.get('sunfluxbot.cache_dir', '/tmp')
  now = time.time()
  image = os.path.join(cache_dir, 'kpi.png')
  chat_id = update.message.chat_id
  today = datetime.now().strftime('%a %b %d %Y')
  try:
    img_st = os.stat(image)
    if now - img_st.st_mtime > 900: # pkindex are published every 5 minutes.
      raise FileNotFoundError
  except (FileNotFoundError, EOFError):
    cmd = os.path.join(sys.path[0], "kpiwwv")
    status = subprocess.call([cmd], shell=False)
    logger.info('Call %s returned %d', cmd, status)
    if status:
      logger.error('Error generating the kpindex graph')
      context.bot.send_message(chat_id, (
        'The kpindex graph is not available at the moment\n'
        'Please come back latter.'))
      return ConversationHandler.END

  context.bot.send_photo(chat_id=chat_id, photo=open(image, 'rb'),
                         caption=f"Planetary KPIndex for: {today}",
                         filename=os.path.basename(image), timeout=100)

  user = update.message.chat.username or "Stranger"
  logger.info("Command /kpindex by %s:%d", user, chat_id)
  return ConversationHandler.END

def send_swx(update: Update, context: CallbackContext):
  filename = noaa_download('swx')
  if not filename:
    update.message.reply_text('The SWX image cannot be displayed at the moment')
    return None

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='Space weather indices',
                         filename=os.path.basename(filename), timeout=100)

  user = update.message.chat.username or "Stranger"
  logger.info("Command /swx by %s:%d", user, chat_id)
  return ConversationHandler.END

def send_swo(update: Update, context: CallbackContext):
  filename = noaa_download('swo')
  if not filename:
    update.message.reply_text('The SWO image cannot be displayed at the moment')
    return ConversationHandler.END

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='Space weather indices overview',
                         filename=os.path.basename(filename), timeout=100)

  user = update.message.chat.username or "Stranger"
  logger.info("Command /swo by %s:%d", user, chat_id)
  return ConversationHandler.END

def send_warn(update: Update, context: CallbackContext):
  filename = noaa_download('warn')
  if not filename:
    update.message.reply_text('The WARN image cannot be displayed at the moment')
    return ConversationHandler.END

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='Space weather warning timelines',
                         filename=os.path.basename(filename), timeout=100)

  user = update.message.chat.username or "Stranger"
  logger.info("Command /warn by %s:%d", user, chat_id)
  return ConversationHandler.END

def send_alerts(update: Update, _context: CallbackContext):
  config = Config()
  cache_dir = config.get('sunfluxbot.cache_dir', '/tmp')
  alert = get_alert(cache_dir)
  update.message.reply_text(alert)

  chat_id = update.message.chat_id
  user = update.message.chat.username or "Stranger"
  logger.info("Command /alerts by %s:%d", user, chat_id)
  return ConversationHandler.END

def dxcc_handler(update: Update, context: CallbackContext):
  try:
    _, continent = update.message.text.split()
    continent = continent.upper()
    if continent not in CONTINENTS:
      raise ValueError
    update.callback_query = type("data", (object,), {"data": continent,})
    send_dxcc(update, context)

  except ValueError:
    keyboard = []
    for key in CONTINENTS:
      keyboard.append(InlineKeyboardButton(key, callback_data=key))
    reply_markup = InlineKeyboardMarkup([keyboard])
    update.message.reply_text('What is your continent?', reply_markup=reply_markup)

def send_dxcc(update: Update, context: CallbackContext):
  query = update.callback_query.data
  if update.message:
    message = update.message
  else:
    message = update.callback_query.message

  chat_id = message.chat.id
  user = message.chat.username or str(chat_id)
  image = f'/tmp/dxcc-{query}-{user}.png'
  now = time.time()
  today = datetime.now().strftime('%a %b %d %Y at %H:%M')

  try:
    img_st = os.stat(image)
    if now - img_st.st_mtime > 300:
      raise FileNotFoundError
  except (FileNotFoundError, EOFError):
    cmd = os.path.join(sys.path[0], "showdxcc")
    status = subprocess.call([cmd, '-c', query, image], shell=False)
    logger.info('Call "%s %s %s" returned %d', cmd, query, image, status)
    if status:
      logger.error('Error generating the dxcc graph')
      context.bot.send_message(chat_id, (
        'The dxcc graph is not available at the moment\n'
        'Please come back latter.'))
      return ConversationHandler.END
  else:
    logger.info('Send %s from cache', image)

  context.bot.send_photo(chat_id=chat_id, photo=open(image, 'rb'),
                         caption=f"DX activity for the last hour on: {today}",
                         filename=os.path.basename(image), timeout=100)

  logger.info("Command /dxcc by %s:%d %s", user, chat_id, query)
  return ConversationHandler.END

def start(update: Update, _context: CallbackContext):
  botname = update.message.bot.first_name
  user = update.message.chat.username or "Stranger"
  chat_id = update.message.chat.id
  lines = [f"Welcome {user} to the {botname} developped by W6BSD",
           "This bot is experimental any feedback is welcome",
           "Use '/help' to see the list of commands"]
  update.message.reply_text('\n'.join(lines))
  logger.info("Command /start by %s:%d", user, chat_id)
  return ConversationHandler.END

def text_handler(update: Update, context: CallbackContext):
  user = update.message.chat.username or "Stranger"
  message = update.message.text
  logger.info(">>> %s sent the message \"%s\"", user, message)
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

def send_legend(update: Update, _context: CallbackContext):
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
  updater.dispatcher.add_handler(CommandHandler('drap', send_drap))
  updater.dispatcher.add_handler(CommandHandler('dxcc', dxcc_handler))
  updater.dispatcher.add_handler(CommandHandler('eisn', send_eisn))
  updater.dispatcher.add_handler(CommandHandler('flux', send_flux))
  updater.dispatcher.add_handler(CommandHandler('geost', send_geost))
  updater.dispatcher.add_handler(CommandHandler('help', help_command))
  updater.dispatcher.add_handler(CommandHandler('kpindex', send_kpindex))
  updater.dispatcher.add_handler(CommandHandler('legend', send_legend))
  updater.dispatcher.add_handler(CommandHandler('muf', send_muf))
  updater.dispatcher.add_handler(CommandHandler('outlook', send_outlook))
  updater.dispatcher.add_handler(CommandHandler('ssn', send_ssn))
  updater.dispatcher.add_handler(CommandHandler('start', start))
  updater.dispatcher.add_handler(CommandHandler('swx', send_swx))
  updater.dispatcher.add_handler(CommandHandler('warning', send_warn))
  updater.dispatcher.add_handler(MessageHandler(Filters.text, text_handler))
  updater.dispatcher.add_handler(CallbackQueryHandler(send_dxcc))
  updater.dispatcher.add_error_handler(error_callback)

  updater.start_polling()
  updater.idle()


if __name__ == "__main__":
  main()
