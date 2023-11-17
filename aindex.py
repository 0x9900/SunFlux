#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c) 2022-2023 Fred W6BSD
# All rights reserved.
#
#

import colorsys
import logging
import os
import pickle
import re
import sqlite3
import sys
import time
import urllib.request

from datetime import datetime, timedelta

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

import adapters

from config import Config

plt.style.use(['classic', 'fast'])

NB_DAYS = 30

NOAA_URL = "https://services.swpc.noaa.gov/text/daily-geomagnetic-indices.txt"

WWV_REQUEST = """
SELECT MAX(wwv.A), AVG(wwv.A), MIN(wwv.A), DATE(DATETIME(wwv.time, "unixepoch")) AS dt
FROM wwv
WHERE wwv.time > ?
GROUP BY dt
"""
WWV_CONDITIONS = "SELECT conditions FROM wwv WHERE time > ? ORDER BY time DESC LIMIT 1"

MAX = 1
AVG = 2
MIN = 3

def color_complement(hue, saturation, value, alpha):
  rgb = colorsys.hsv_to_rgb(hue, saturation, value)
  c_rgb = [1.0 - c for c in rgb]
  c_hsv = colorsys.rgb_to_hsv(*c_rgb)
  return c_hsv + (alpha, )


def get_conditions(config):
  db_name = config['db_name']
  start_time = datetime.utcnow() - timedelta(days=1)
  conn = sqlite3.connect(db_name, timeout=5,
                         detect_types=sqlite3.PARSE_DECLTYPES)
  with conn:
    curs = conn.cursor()
    result = curs.execute(WWV_CONDITIONS, (start_time,)).fetchone()
    try:
      conditions = result[0]
    except TypeError:
      return None
  if re.match(r'(No Storm.*){2}', conditions):
    return None
  return conditions


def download_aindex(cache_file):
  data = {}
  with urllib.request.urlopen(NOAA_URL) as res:
    encoding = res.info().get_content_charset('utf-8')
    for line in res:
      line = line.decode(encoding)
      if line.startswith(':') or line.startswith('#'):
        continue
      try:
        date = datetime.strptime(f"{line[0:10]}", "%Y %m %d")
        aindex = sorted([float(line[11:17]), float(line[33:40]), float(line[57:63])])
        data[date] = tuple([max(aindex), sum(aindex)/len(aindex), min(aindex)])
      except ValueError:
        pass

  with open(cache_file, 'wb') as cfd:
    pickle.dump(data, cfd)


def get_noaa(config):
  cache_file = config.get('cache_file', '/tmp/aindex-noaa.pkl')
  cache_time = config.get('cache_time', 3600*12)
  days = config.get('nb_days', NB_DAYS)
  now = time.time()
  start_date = datetime.utcnow() - timedelta(days=days)

  try:
    filest = os.stat(cache_file)
    if now - filest.st_mtime > cache_time:
      raise FileNotFoundError
  except FileNotFoundError:
    download_aindex(cache_file)

  with open(cache_file, 'rb') as cfd:
    _data = pickle.load(cfd)

  data = {}
  for date, values in _data.items():
    if date >= start_date:
      data[date] = values
  return data


def get_wwv(config):
  db_name = config.get('db_name')
  days = config.get('nb_days', NB_DAYS)
  start_date = datetime.utcnow() - timedelta(days=days)
  data = {}

  conn = sqlite3.connect(db_name, timeout=5,
                         detect_types=sqlite3.PARSE_DECLTYPES)
  with conn:
    curs = conn.cursor()
    results = curs.execute(WWV_REQUEST, (start_date.timestamp(),))
    for res in results:
      try:
        date = datetime.strptime(res[-1], '%Y-%m-%d')
        data[date] = res[:-1]
      except TypeError:
        pass
  return data


def autolabel(ax, rects):
  """Attach a text label above each bar displaying its height"""
  for rect in rects:
    height = rect.get_height()
    color = rect.get_facecolor()
    ax.text(rect.get_x() + rect.get_width() / 2., 1, f'{int(height)}',
            color=color_complement(*color), fontsize="10", ha='center')


def graph(data, condition, filename):
  values = np.row_stack(list(data.values()))
  keys_column = np.array(list(data.keys())).reshape((-1, 1))
  data = np.hstack((keys_column, values))

  colors = ['lightgreen'] * data[:,0].size
  for pos, val in enumerate(data[:,AVG]):
    if 20 < val < 30:
      colors[pos] = 'darkorange'
    elif 30 < val < 50:
      colors[pos] = 'red'
    elif 50 < val < 100:
      colors[pos] = 'darkred'
    elif val >= 100:
      colors[pos] = 'darkmagenta'

  today = datetime.utcnow().strftime('%Y/%m/%d %H:%M UTC')
  fig = plt.figure(figsize=(12, 5))
  fig.suptitle('A-Index', fontsize=14, fontweight='bold')
  fig.text(0.01, 0.02, f'SunFluxBot By W6BSD {today}')
  if condition:
    fig.text(0.15, 0.8, "Forecast: " + condition, fontsize=12, zorder=4,
             bbox={'boxstyle': 'round', 'linewidth': 1, 'facecolor': 'linen', 'alpha': 1,
                    'pad': 0.8})

  axgc = plt.gca()
  axgc.tick_params(labelsize=10)
  bars = axgc.bar(data[:,0], data[:,AVG], linewidth=0.75, zorder=2, color=colors)
  axgc.plot(data[:,0], data[:,MAX], marker='v', linewidth=0, color="steelblue")
  axgc.plot(data[:,0], data[:,MIN], marker='^', linewidth=0, color="navy")
  autolabel(axgc, bars)

  axgc.axhline(y=20, linewidth=1.5, zorder=1, color='green')
  axgc.axhline(y=30, linewidth=1.5, zorder=1, color='darkorange')
  axgc.axhline(y=40, linewidth=1.5, zorder=1, color='red')
  axgc.axhline(y=50, linewidth=1.5, zorder=1, color='darkred')
  axgc.axhline(y=100, linewidth=1.5, zorder=1, color='darkmagenta')

  loc = mdates.DayLocator(interval=2)
  axgc.xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d UTC'))
  axgc.xaxis.set_major_locator(loc)
  axgc.xaxis.set_minor_locator(mdates.DayLocator())
  axgc.set_ylim(0, data[:,MAX].max() * 1.1)
  axgc.set_ylabel('A-Index')
  axgc.grid(color="gray", linestyle="dotted", linewidth=.5)
  axgc.margins(.01)

  axgc.legend(['Max', 'Min'], loc='upper right', fontsize='10',
              facecolor='linen', borderaxespad=1)

  fig.autofmt_xdate(rotation=10, ha="center")
  plt.savefig(filename, transparent=False, dpi=100)
  plt.close()
  return filename


def main():
  _config = Config()
  config = _config.get('aindex')
  del _config

  adapters.install_adapters()
  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)3d - %(levelname)s - %(message)s', datefmt='%x %X',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )
  logger = logging.getLogger('aindex')

  try:
    name = sys.argv[1]
  except IndexError:
    name = '/tmp/aindex.png'

  data = get_noaa(config)
  data.update(get_wwv(config))
  condition = get_conditions(config)

  if data:
    graph(data, condition, name)
    logger.info('Graph "%s" saved', name)
  else:
    logger.warning('No data collected')


if __name__ == "__main__":
  sys.exit(main())
