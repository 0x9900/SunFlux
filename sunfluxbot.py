#!/usr/bin/env python3.9
#
#

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
  Filters,
  MessageHandler,
  Updater,
)

import showdxcc

logging.basicConfig(
  format='%(asctime)s %(module)s %(levelname)s: %(message)s',
  datefmt='%H:%M:%S',
  level=logging.getLevelName(os.getenv('LEVEL', 'INFO'))
)
logger = logging.getLogger(__name__)

NOAA_URL = 'https://services.swpc.noaa.gov'
ALERTS_URL = NOAA_URL + "/text/wwv.txt"

NOAA_URL = "https://services.swpc.noaa.gov/"
IMG_SOURCE = {
  'ai':    'images/station-a-index.png',
  'gef':   'images/animations/geoelectric/US-Canada/EmapGraphics_1m/latest.png',
  'geost': 'images/geospace/geospace_7_day.png',
  'ki':    'images/station-k-index.png',
  'swx':   'images/swx-overview-large.gif',
  'tec':   'images/animations/ctipe/tec/latest.png',
  'swo':   'images/swx-overview-large.gif',
  'warn':  'images/notifications-timeline.png',
}

class NoaaData:
  """Data structure storing all the sun indices predictions"""

  def __init__(self):
    self.date = None
    self.fields = []

  def __cmp__(self, other):
    return (self.date > other.date) - (self.date < other.date)

  def __eq__(self, other):
    if other is None:
      return False
    return self.date == other.date


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

class Alerts:
  """NOAA space weather alerts"""

  def __init__(self, cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
    cachefile = os.path.join(cache_dir, 'alerts.pkl')
    self.data = None

    cached_data = readcache(cachefile)
    self.data = self.download()

    if self.data == cached_data:
      self.newdata = False
    else:
      self.newdata = True
      writecache(cachefile, self.data)

  @staticmethod
  def download():
    try:
      req = urllib.request.urlopen(ALERTS_URL)
      webdata = req.read()
      encoding = req.info().get_content_charset('utf-8')
      webdata = webdata.decode(encoding)
    except urllib.request.URLError as err:
      logging.error('Connection error: %s we will try later', err)
      return

    alerts = NoaaData()
    if req.status == 200:
      for line in webdata.splitlines():
        line = line.strip()
        if line.startswith(':Issued'):
          alerts.date = datetime.strptime(line, ':Issued: %Y %b %d %H%M %Z')
          continue
        if not line or line.startswith(':') or line.startswith('#'):
          continue
        alerts.fields.append(line)

    return alerts

  def __repr__(self):
    return "<{}> at: {}".format(self.__class__.__name__, self.time.isoformat())

  @property
  def time(self):
    return self.data.date

  @property
  def text(self):
    return '\n'.join(f for f in self.data.fields if not f.startswith('No space weather'))


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
    if now - filest.st_atime > 900:
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
  logger.warning('error_callback - Update "%s" error "%s"', update, context.error)

def help_command(update: Update, context: CallbackContext):
  help = [
    "*Use the following commands:*",
    "> /aindex: A Index",
    "> /alerts: NOAA Alerts",
    "> /dxcc: Show dxcc contacts",
    "> /flux: 10cm Flux",
    "> /gef: GeoElectric Field",
    "> /geost: GeoSpace Timeline",
    "> /kindex: K Index",
    "> /swx: Solar indices overvew",
    "> /tec: Total Electron Content",
    "> /warning: Warning timelines",
    "\n*Propagation information:*",
    "> _For best radio propagation_",
    "> `Flux >= 80, KIndex >= 3, AIndex >= 10`",
    "\n_For more information see /credits_"
  ]
  update.message.reply_text("\n".join(help), parse_mode='Markdown')
  user = update.message.chat.username.upper()
  chat_id = update.message.chat.id
  logger.info(f"Command /help by {user}:{chat_id}")

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
  ]
  update.message.reply_text("\n".join(credits), parse_mode='Markdown')

def send_flux(update: Update, context: CallbackContext):
  config = Config
  cache_dir = config.get('sunfluxbot.cache_dir', '/tmp')
  now = time.time()
  image = os.path.join(cache_dir, 'flux.png')
  try:
    img_st = os.stat(image)
    if now - img_st.st_atime > 3600:
      raise FileNotFoundError
  except (FileNotFoundError, EOFError):
    cmd = os.path.join(os.getcwd(), "flux.py")
    value = subprocess.call([cmd], shell=True)
    logging.info(f'Call {cmd} returned {value}')
    if value:
      logging.error('Error generating the flux graph')
      return

  chat_id = update.message.chat_id
  today = datetime.now().strftime('%a %b %d %Y')
  context.bot.send_photo(chat_id=chat_id, photo=open(image, 'rb'),
                         caption="10cm flux for: {}".format(today),
                         filename=os.path.basename(image), timeout=100)

def send_tec(update: Update, context: CallbackContext):
  try:
    filename = noaa_download('tec')
  except Exception as exp:
    logger.error(exp)
    update.message.reply_text(f'Error: {exp}')
    return

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='Total Electron Content',
                         filename=os.path.basename(filename), timeout=100)

def send_geost(update: Update, context: CallbackContext):
  try:
    filename = noaa_download('geost')
  except Exception as exp:
    logger.error(exp)
    update.message.reply_text(f'Error: {exp}')
    return

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='Geospace timeline',
                         filename=os.path.basename(filename), timeout=100)

def send_gef(update: Update, context: CallbackContext):
  try:
    filename = noaa_download('gef')
  except Exception as exp:
    logger.error(exp)
    update.message.reply_text(f'Error: {exp}')
    return

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='Geoelectric field',
                         filename=os.path.basename(filename), timeout=100)

def send_ai(update: Update, context: CallbackContext):
  try:
    filename = noaa_download('ai')
  except Exception as exp:
    logger.error(exp)
    update.message.reply_text(f'Error: {exp}')
    return

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='A Index',
                         filename=os.path.basename(filename), timeout=100)

def send_ki(update: Update, context: CallbackContext):
  try:
    filename = noaa_download('ki')
  except Exception as exp:
    logger.error(exp)
    update.message.reply_text(f'Error: {exp}')
    return

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='K index',
                         filename=os.path.basename(filename), timeout=100)

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
    return

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='Space weather indices overview',
                         filename=os.path.basename(filename), timeout=100)

def send_warn(update: Update, context: CallbackContext):
  try:
    filename = noaa_download('warn')
  except Exception as exp:
    logger.error(exp)
    update.message.reply_text(f'Error: {exp}')
    return

  chat_id = update.message.chat_id
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='Space weather warning timelines',
                         filename=os.path.basename(filename), timeout=100)

def send_alerts(update: Update, context: CallbackContext):
  config = Config()
  cache_dir = config.get('sunfluxbot.cache_dir', '/tmp')
  alerts = Alerts(cache_dir)
  update.message.reply_text(alerts.text)

def dxcc_handler(update: Update, context: CallbackContext):
  keyboard = []
  for key in showdxcc.CONTINENTS:
    keyboard.append(InlineKeyboardButton(key, callback_data=key))
  reply_markup = InlineKeyboardMarkup([keyboard])
  update.message.reply_text('What is your continent?', reply_markup=reply_markup)


def send_dxcc(update: Update, context: CallbackContext):
  query = update.callback_query
  user = query.message.chat.username
  chat_id = query.message.chat.id
  filename = f'/tmp/dxcc-{user}.png'
  showdxcc.get_dxcc(query.data, filename)
  context.bot.send_photo(chat_id=chat_id, photo=open(filename, "rb"),
                         caption='DXCC contacts',
                         filename=os.path.basename(filename), timeout=100)


def start(update: Update, context: CallbackContext):
  botname = update.message.bot.first_name
  user = update.message.chat.username.upper()
  chat_id = update.message.chat.id
  lines = [f"Welcome {user} to the {botname} developped by W6BSD",
           "This bot is experimental any feedback is welcome",
           "Use '/help' to see the list of commands"]
  update.message.reply_text('\n'.join(lines))
  logger.info(f"Command /start by {user}:{chat_id}")

def text_handler(update: Update, context: CallbackContext):
  user = update.message.chat.username
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

def main():
  config = Config()
  updater = Updater(config['sunfluxbot.token'])
  updater.bot.logger.level = logging.INFO
  updater.dispatcher.add_handler(CommandHandler('ai', send_ai))
  updater.dispatcher.add_handler(CommandHandler('aindex', send_ai))
  updater.dispatcher.add_handler(CommandHandler('alert', send_alerts))
  updater.dispatcher.add_handler(CommandHandler('alerts', send_alerts))
  updater.dispatcher.add_handler(CommandHandler('credits', send_credits))
  updater.dispatcher.add_handler(CommandHandler('dxcc', dxcc_handler))
  updater.dispatcher.add_handler(CommandHandler('flux', send_flux))
  updater.dispatcher.add_handler(CommandHandler('gef', send_gef))
  updater.dispatcher.add_handler(CommandHandler('geost', send_geost))
  updater.dispatcher.add_handler(CommandHandler('help', help_command))
  updater.dispatcher.add_handler(CommandHandler('ki', send_ki))
  updater.dispatcher.add_handler(CommandHandler('kindex', send_ki))
  updater.dispatcher.add_handler(CommandHandler('start', start))
  updater.dispatcher.add_handler(CommandHandler('swx', send_swx))
  updater.dispatcher.add_handler(CommandHandler('tec', send_tec))
  updater.dispatcher.add_handler(CommandHandler('warning', send_warn))
  updater.dispatcher.add_handler(MessageHandler(Filters.text, text_handler))
  updater.dispatcher.add_handler(CallbackQueryHandler(send_dxcc))
  updater.dispatcher.add_error_handler(error_callback)

  updater.start_polling()
  updater.idle()


if __name__ == "__main__":
  main()
