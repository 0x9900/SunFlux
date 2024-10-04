#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c)2022-2023 Fred W6BSD
# All rights reserved.
#
#

import argparse
import json
import logging
import os
import pathlib
import re
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.request import urlretrieve

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MultipleLocator

import adapters
import tools
from config import Config

NOAA_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"

NB_DAYS = 5

WWV_REQUEST = "SELECT wwv.time, wwv.k FROM wwv WHERE wwv.time > ?"
WWV_CONDITIONS = ("SELECT conditions FROM wwv WHERE time > ? "
                  "ORDER BY time DESC LIMIT 1")


logging.basicConfig(
  format='%(asctime)s %(levelname)s - %(name)s:%(lineno)3d - %(message)s', datefmt='%x %X',
  level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
)
logger = logging.getLogger('pkiwwv')


def bucket(dtm, size=4):
  return int(size * int(dtm.hour / size))


def get_conditions(config):
  db_name = config['db_name']
  start_time = datetime.now(timezone.utc) - timedelta(hours=12)
  conn = sqlite3.connect(db_name, timeout=5, detect_types=sqlite3.PARSE_DECLTYPES)
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


def get_pkindex(config):
  data = defaultdict(list)
  cache_file = config.get('cache_file', '/tmp/pkiwwv-noaa.json')
  cache_time = config.get('cache_time', 10800)
  days = config.get('nb_days', NB_DAYS)
  start_date = datetime.now(timezone.utc) - timedelta(days=days)
  now = time.time()

  try:
    filest = os.stat(cache_file)
    if now - filest.st_mtime > cache_time:
      raise FileNotFoundError
  except FileNotFoundError:
    urlretrieve(NOAA_URL, cache_file)

  with open(cache_file, 'r', encoding='ASCII') as cfd:
    _data = json.load(cfd)

  for rec in _data:
    try:
      date = datetime.strptime(rec[0], '%Y-%m-%d %H:%M:%S.%f')
      date = date.replace(hour=bucket(date), minute=0, second=0, microsecond=0,
                          tzinfo=timezone.utc)
      if date >= start_date:
        data[date].append(float(rec[1]))
    except ValueError:
      pass

  return data


def get_wwv(config):
  data = defaultdict(list)
  days = config.get('nb_days', NB_DAYS)
  start_date = datetime.now(timezone.utc) - timedelta(days=days)

  conn = sqlite3.connect(config['db_name'], timeout=5,
                         detect_types=sqlite3.PARSE_DECLTYPES)
  with conn:
    curs = conn.cursor()
    results = curs.execute(WWV_REQUEST, (start_date,))
    for elem in results:
      date = elem[0]
      date = date.replace(hour=bucket(date), minute=0, second=0,
                          microsecond=0, tzinfo=timezone.utc)
      data[date].append(elem[1])

  return data


def graph(data, condition, filename):
  # pylint: disable=too-many-locals
  values = np.full((len(data), 3), np.nan, dtype=object)
  for i, row in enumerate(data.values()):
    row = np.array(row)
    avg = np.average(row)
    avg = avg if avg > 0 else 0.1
    values[i, :3] = [np.min(row), avg, np.max(row)]

  key_dates = np.array(list(data.keys())).reshape((-1, 1))
  data = np.hstack((key_dates, values))

  # I should use mpl.colormaps here
  # colors #6efa7b #a7bb36 #aa7f28 #8c4d30 #582a2d
  colors = ['#8EBA42'] * data[:, 0].size
  for pos, val in enumerate(data[:, 2]):
    if 4 <= val < 5:
      colors[pos] = '#a7bb36'
    elif 5 <= val < 6:
      colors[pos] = '#aa7f28'
    elif 6 <= val < 8:
      colors[pos] = '#8c4d30'
    elif val >= 8:
      colors[pos] = '#582a2d'

  fig = plt.figure(figsize=(12, 5))
  fig.suptitle('Planetary K-Index')
  if condition:
    box = {"facecolor": 'white', "alpha": 0.75, "linewidth": 0}
    fig.text(0.136, 0.68, "Forecast: " + condition, fontsize=10, zorder=4,
             fontweight='bold', color='red', bbox=box)

  axgc = plt.gca()
  axgc.plot(data[:, 0], data[:, 1], marker='v', linewidth=0, zorder=3, color="#988ED5")
  axgc.bar(data[:, 0], data[:, 2], width=0.14, linewidth=0.75, zorder=2, color=colors)
  axgc.plot(data[:, 0], data[:, 3], marker='^', linewidth=0, zorder=4, color="#E24A33")

  axgc.axhline(y=4, linewidth=1.5, zorder=1, color='red', label='Threshold')

  loc = mdates.DayLocator(interval=1)
  axgc.xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d UTC'))
  axgc.xaxis.set_major_locator(loc)
  axgc.xaxis.set_minor_locator(mdates.DayLocator())
  axgc.yaxis.set_major_locator(MultipleLocator(1))

  axgc.set_ylim(0, 9.5)
  axgc.set_ylabel('K-Index')
  axgc.margins(.01)

  axgc.legend(['Min', 'Max', 'Storm Threshold'], loc='upper left', borderaxespad=1)
  fig.autofmt_xdate(rotation=10, ha="center")

  tools.save_plot(plt, filename)
  plt.close()


def main():
  adapters.install_adapters()
  config = Config().get('pkiwwv', {})
  target_dir = config.get('target_dir', '/var/www/html')

  parser = argparse.ArgumentParser()
  parser.add_argument('-D', '--days', default=config.get('nb_days', NB_DAYS), type=int,
                      help='Number of days to graph [Default: %(default)s]')
  parser.add_argument('-c', '--cluster', action="store_true", default=False,
                      help='Add data coming from the cluster network [Default: %(default)s]')
  parser.add_argument('-t', '--target', type=pathlib.Path, default=target_dir,
                      help='Image path')
  opts = parser.parse_args()

  config['nb_days'] = opts.days

  data = get_pkindex(config)
  if opts.cluster:
    data.update(get_wwv(config))
  condition = get_conditions(config)

  if not data:
    logger.warning('No data collected')
    return os.EX_DATAERR

  styles = tools.STYLES
  for style in styles:
    with plt.style.context(style.style):
      filename = opts.target.joinpath(f'pkindex-{style.name}')
      graph(data, condition, filename)
      if style.name == 'light':
        tools.mk_link(filename, opts.target.joinpath('pkindex'))

  return os.EX_OK


if __name__ == "__main__":
  sys.exit(main())
