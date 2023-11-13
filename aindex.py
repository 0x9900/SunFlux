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

NB_DAYS = 34

NOAA_URL = "https://services.swpc.noaa.gov/text/daily-geomagnetic-indices.txt"

WWV_REQUEST = """
SELECT MAX(wwv.A), AVG(wwv.A), MIN(wwv.A), DATE(DATETIME(wwv.time, "unixepoch")) AS dt
FROM wwv
WHERE wwv.time > ?
GROUP BY dt
"""
WWV_CONDITIONS = "SELECT conditions FROM wwv WHERE time > ? ORDER BY time DESC LIMIT 1"


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
        aindex = sorted([int(line[11:17]), int(line[33:40]), int(line[57:63])])
        data[date] = tuple(aindex)
      except ValueError:
        pass

  with open(cache_file, 'wb') as cfd:
    pickle.dump(data, cfd)


def get_aindex(config):
  cache_file = config.get('aindex.cache_file', '/tmp/aindex-noaa.pkl')
  cache_time = config.get('aindex.cache_time', 3600*12)
  now = time.time()

  try:
    filest = os.stat(cache_file)
    if now - filest.st_mtime > cache_time:
      raise FileNotFoundError
  except FileNotFoundError:
    download_aindex(cache_file)

  with open(cache_file, 'rb') as cfd:
    _data = pickle.load(cfd)

  return _data

def get_wwv(config):
  noaa_aindex = get_aindex(config)
  db_name = config['db_name']
  days = config.get('nb_days', NB_DAYS)
  start_date = datetime.utcnow() - timedelta(days=days)
  data = {}
  for date, values in noaa_aindex.items():
    if date >= start_date:
      data[date] = values

  conn = sqlite3.connect(db_name, timeout=5,
                         detect_types=sqlite3.PARSE_DECLTYPES)
  with conn:
    curs = conn.cursor()
    results = curs.execute(WWV_REQUEST, (start_date.timestamp(),))
    for res in results:
      date = datetime.strptime(res[-1], '%Y-%m-%d')
      data[date] = res[:-1]
  return [(d, *v) for d, v in data.items()]


def autolabel(ax, rects):
  """Attach a text label above each bar displaying its height"""
  for rect in rects:
    height = rect.get_height()
    color = rect.get_facecolor()
    ax.text(rect.get_x() + rect.get_width() / 2., 1, f'{int(height)}',
            color=color_complement(*color), fontsize="10", ha='center')


def graph(data, condition, filename):
  datetm = np.array([d[0] for d in data])
  amax = np.array([d[1] for d in data])
  amin = np.array([d[3] for d in data])
  aavg = np.array([d[2] for d in data])

  colors = ['lightgreen'] * len(aavg)
  for pos, val in enumerate(aavg):
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
  bars = axgc.bar(datetm, aavg, linewidth=0.75, zorder=2, color=colors)
  axgc.plot(datetm, amax, marker='v', linewidth=0, color="steelblue")
  axgc.plot(datetm, amin, marker='^', linewidth=0, color="navy")
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

  axgc.set_ylim(0, max(amax) * 1.15)
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

  data = get_wwv(config)
  condition = get_conditions(config)
  if data:
    graph(data, condition, name)
    logger.info('Graph "%s" saved', name)
  else:
    logger.warning('No data collected')


if __name__ == "__main__":
  sys.exit(main())
