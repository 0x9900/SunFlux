#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c) 2022 Fred W6BSD
# All rights reserved.
#
#

import argparse
import logging
import os
import sqlite3
import sys

from collections import defaultdict
from datetime import datetime, timedelta

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

import adapters

from config import Config

plt.style.use(['classic', 'seaborn-talk'])

NB_DAYS = 92

WWV_REQUEST = "SELECT wwv.time, wwv.SFI FROM wwv WHERE wwv.time > ?"


def bucket(dtm, size=8):
  return int(size * int(dtm.hour / size))


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

  for fun in (y.argmax, y.argmin, lambda: x.size - 1):
    pos = fun()
    xytext = (-20, 20) if pos == x.size -1 else (20,-20)
    plt.annotate(f"{y[pos]:d}", (x[pos], y[pos]), textcoords="offset points", xytext=xytext,
                 ha='center', fontsize=10,
                 arrowprops=dict(arrowstyle="wedge", color='dimgray'),
                 bbox=dict(boxstyle="square,pad=0.2", fc="white"))

  loc = mdates.DayLocator(interval=10)
  axgc.xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d UTC'))
  axgc.xaxis.set_major_locator(loc)
  axgc.xaxis.set_minor_locator(mdates.DayLocator())
  axgc.set_ylabel('SFU at 2800 MHz', fontsize=12)

  ticks = np.array([50, 70])
  ticks = np.append(ticks, np.arange(90, int(y.max() * 1.10), 10))
  axgc.set_yticks(ticks)

  zone1 = axgc.axhspan(90, ticks.max(), facecolor='lightgreen', alpha=0.3, label='Good')
  zone2 = axgc.axhspan(70, 90, facecolor='orange', alpha=0.3, label='Ok')
  zone3 = axgc.axhspan(40, 70, facecolor='red', alpha=0.3, label='Bad')

  trend_legend = axgc.legend(handles=[trend], fontsize=10, loc='upper right')
  axgc.add_artist(trend_legend)
  axgc.legend(handles=[zone1, zone2, zone3], fontsize=10, loc="upper left")

  axgc.grid(color="gray", linestyle="dotted", linewidth=.5)
  axgc.margins(x=.015)

  fig.autofmt_xdate(rotation=10, ha="center")
  plt.figtext(0.02, 0.02, f'SunFluxBot By W6BSD {date}')
  plt.savefig(filename, transparent=False, dpi=100)
  plt.close()
  return filename


def main():
  adapters.install_adapers()
  logging.basicConfig(format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s',
                      datefmt='%H:%M:%S')
  logger = logging.getLogger('fluxgraph')
  logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))
  config = Config()

  parser = argparse.ArgumentParser()
  parser.add_argument('-D', '--days', default=NB_DAYS, type=int,
                      help='Number of days to graph [Default: %(default)s]')
  parser.add_argument('name', help='Name of the graph', nargs="*", default=['/tmp/flux.png'])
  opts = parser.parse_args()

  data = get_flux(config, opts.days)
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
