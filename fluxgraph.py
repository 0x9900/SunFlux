#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c) 2022-2023 Fred W6BSD
# All rights reserved.
#
#

import argparse
import json
import logging
import os
import pickle
import sqlite3
import sys
import urllib.request

from collections import defaultdict
from datetime import datetime, timedelta

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

import adapters
import tools

from config import Config

plt.style.use(['classic', 'fast'])

NB_DAYS = 92
MIN_TICKS = 55

WWV_REQUEST = "SELECT wwv.time, wwv.SFI FROM wwv WHERE wwv.time > ?"

NOAA_URL = 'https://services.swpc.noaa.gov/json/f107_cm_flux.json'

def bucket(dtm, size=8):
  return int(size * int(dtm.hour / size))

def download_flux(config, days=NB_DAYS):
  # This function will be completely rewriten once we have more data.
  cache_file = config.get('fluxgraph.cache_file', '/tmp/flux_data.pkl')
  try:
    with open(cache_file, 'rb') as fdf:
      data_flux = pickle.load(fdf)
  except FileNotFoundError:
    data_flux = defaultdict(list)

  with urllib.request.urlopen(NOAA_URL) as res:
    webdata = res.read()
    encoding = res.info().get_content_charset('utf-8')
    _data = json.loads(webdata.decode(encoding))

  data = defaultdict(list)
  for elem in _data:
    date = tools.noaa_date(elem['time_tag']+'Z')
    date = date.replace(hour=bucket(date), minute=0, second=0, microsecond=0)
    data[date].append(elem['flux'])

  data_flux.update(data)
  try:
    with open(cache_file, 'wb') as fdf:
      pickle.dump(data_flux, fdf)
  except OSError as err:
    logging.error(err)

  start_date = datetime.utcnow() - timedelta(days=days)
  selected = {k: v for k, v in data_flux.items() if k >= start_date}
  return sorted(selected.items())


def get_flux(config, days=NB_DAYS):
  data = defaultdict(list)
  start_date = datetime.utcnow() - timedelta(days=days)
  conn = sqlite3.connect(config['showdxcc.db_name'], timeout=5,
                         detect_types=sqlite3.PARSE_DECLTYPES)
  with conn:
    curs = conn.cursor()
    results = curs.execute(WWV_REQUEST, (start_date,))
    for elem in results:
      date = elem[0]
      date = date.replace(hour=bucket(date), minute=0, second=0, microsecond=0)
      data[date].append(elem[1])

  return sorted(data.items())


def graph(data, filename):
  # pylint: disable=invalid-name, too-many-locals
  x = np.array([mdates.date2num(d[0]) for d in data])
  y = np.array([round(np.mean(d[1])) for d in data])
  p = np.poly1d(np.polyfit(x, y, int(y.size/64)))

  date = datetime.utcnow().strftime('%Y/%m/%d %H:%M UTC')
  fig = plt.figure(figsize=(12, 5))
  fig.suptitle('Daily 10cm Flux Index', fontsize=14, fontweight='bold')
  axgc = plt.gca()
  axgc.plot(x, y, linewidth=1.5, label='Flux')
  trend, = axgc.plot(x, p(x), label='Trend', linestyle='--', color="red", linewidth=2)
  axgc.tick_params(labelsize=10)

  for pos in set([y.argmax(), y.argmin(), x.size - 1]):
    xytext = (20, 20) if pos == x.size -1 else (20,-20)
    plt.annotate(f"{y[pos]:d}", (x[pos], y[pos]), textcoords="offset points", xytext=xytext,
                 ha='center', fontsize=10,
                 arrowprops=dict(arrowstyle="wedge", color='dimgray'),
                 bbox=dict(boxstyle="square,pad=0.2", fc="white"))

  loc = mdates.DayLocator(interval=10)
  axgc.xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d UTC'))
  axgc.xaxis.set_major_locator(loc)
  axgc.xaxis.set_minor_locator(mdates.DayLocator())
  axgc.set_ylabel('SFU at 2800 MHz', fontsize=12)
  axgc.set_ylim([MIN_TICKS, y.max() * 1.15])

  ticks = np.array([MIN_TICKS, 70])
  ticks = np.append(ticks, np.arange(90, int(y.max() * 1.15), 20))
  axgc.set_yticks(ticks)

  zone1 = axgc.axhspan(90, round(axgc.axis()[-1]), facecolor='lightgreen', alpha=0.3, label='Good')
  zone2 = axgc.axhspan(70, 90, facecolor='orange', alpha=0.3, label='Ok')
  zone3 = axgc.axhspan(MIN_TICKS, 70, facecolor='red', alpha=0.3, label='Bad')

  trend_legend = axgc.legend(handles=[trend], fontsize=10, loc='lower left')
  axgc.add_artist(trend_legend)
  axgc.legend(handles=[zone1, zone2, zone3], fontsize=10, loc="upper left")

  axgc.grid(color="gray", linestyle="dotted", linewidth=.5)
  axgc.margins(x=.015)

  fig.autofmt_xdate(rotation=10, ha="center")
  plt.figtext(0.01, 0.02, f'SunFluxBot By W6BSD {date}')
  plt.savefig(filename, transparent=False, dpi=100)
  plt.close()
  return filename


def main():
  adapters.install_adapters()
  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)3d - %(levelname)s - %(message)s', datefmt='%x %X',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )
  logger = logging.getLogger('fluxgraph')
  logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))
  config = Config()

  parser = argparse.ArgumentParser()
  parser.add_argument('-D', '--days', default=NB_DAYS, type=int,
                      help='Number of days to graph [Default: %(default)s]')
  parser.add_argument('name', help='Name of the graph', nargs="*", default=['/tmp/flux.png'])
  opts = parser.parse_args()

  # data = get_flux(config, opts.days)
  data = download_flux(config, days=NB_DAYS)
  if not data:
    logger.warning('No data collected')
    return os.EX_DATAERR

  logger.debug('Dataset size: %d', len(data))
  name = opts.name.pop(0)
  graph(data, name)
  logger.info('Graph "%s" saved', name)
  return os.EX_OK

if __name__ == "__main__":
  sys.exit(main())
