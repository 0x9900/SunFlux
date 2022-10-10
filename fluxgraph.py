#!/usr/bin/env python3.9
#
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

NB_DAYS = 90

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
  # pylint: disable=invalid-name
  x = np.array([mdates.date2num(d[0]) for d in data])
  y = np.array([round(np.mean(d[1])) for d in data])
  p = np.poly1d(np.polyfit(x, y, int(y.size/64)))

  date = datetime.utcnow().strftime('%Y/%m/%d %H:%M UTC')
  fig = plt.figure(figsize=(12, 5))
  fig.suptitle('Daily 10cm Flux Index', fontsize=14, fontweight='bold')
  axgc = plt.gca()
  axgc.plot(x, y)
  axgc.plot(x, p(x), linestyle='--', color="red", linewidth=2)
  axgc.tick_params(labelsize=10)

  plt.annotate(f"{y[-1]:d}", (x[-1], y[-1]), textcoords="offset points", xytext=(-20, 30),
               ha='center', fontsize=10,
               arrowprops=dict(arrowstyle="wedge", color='dimgray'),
               bbox=dict(boxstyle="square,pad=0.2", fc="white"))
  for fun in (np.argmax, np.argmin):
    pos = fun(y)
    if pos == y.size -1:
      continue
    plt.annotate(f"{y[pos]:d}", (x[pos], y[pos]), textcoords="offset points", xytext=(30,-20),
                 ha='center', fontsize=10,
                 arrowprops=dict(arrowstyle="wedge", color='dimgray'),
                 bbox=dict(boxstyle="square,pad=0.2", fc="white"))

  loc = mdates.DayLocator(interval=7)
  axgc.xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d UTC'))
  axgc.xaxis.set_major_locator(loc)
  axgc.xaxis.set_minor_locator(mdates.DayLocator())

  ticks = np.array([50, 70])
  ticks = np.append(ticks, np.arange(90, int(y.max() * 1.15), 25))
  axgc.set_yticks(ticks)

  axgc.axhspan(90, ticks.max(), facecolor='lightgreen', alpha=0.3, label='Good')
  axgc.axhspan(70, 90, facecolor='orange', alpha=0.3, label='Ok')
  axgc.axhspan(40, 70, facecolor='red', alpha=0.3, label='Bad')
  axgc.legend(fontsize=10, loc="upper left")

  axgc.grid(color="gray", linestyle="dotted", linewidth=.5)
  axgc.margins(x=.015)

  fig.autofmt_xdate(rotation=10, ha="center")
  plt.figtext(0.02, 0.02, f'SunFluxBot By W6BSD {date}')
  plt.savefig(filename, transparent=False, dpi=100)
  plt.close()
  return filename


def main():
  adapters.install_adapers()
  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s', datefmt='%H:%M:%S',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )
  logger = logging.getLogger('fluxgraph')
  config = Config()
  try:
    name = sys.argv[1]
  except IndexError:
    name = '/tmp/flux.png'

  data = get_flux(config)
  if not data:
    logger.warning('No data collected')
    return os.EX_DATAERR

  graph(data, name)
  logger.info('Graph "%s" saved', name)
  return os.EX_OK

if __name__ == "__main__":
  sys.exit(main())
