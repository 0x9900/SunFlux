#!/usr/bin/env python3.9
#
import logging
import os
import sqlite3
import sys

from datetime import datetime, timedelta

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

import adapters

from config import Config

plt.style.use(['classic', 'seaborn-talk'])

NB_DAYS = 90

WWV_REQUEST = """
SELECT MAX(wwv.A), wwv.conditions, DATE(DATETIME(wwv.time, "unixepoch")) AS dt
FROM wwv
WHERE wwv.time > ?
GROUP BY dt
"""

def get_wwv(config, days):
  start_date = datetime.utcnow() - timedelta(days=days)
  conn = sqlite3.connect(
    config['showdxcc.db_name'], timeout=5,
    detect_types=sqlite3.PARSE_DECLTYPES
  )
  with conn:
    curs = conn.cursor()
    results = curs.execute(WWV_REQUEST, (start_date,)).fetchall()

  data = []
  for res in results:
    dte = datetime.strptime(res[2], '%Y-%m-%d')
    data.append((dte, res[0], res[1]))
  return data

def graph(data, filename):

  datetm = np.array([d[0] for d in data])
  aindex = np.array([d[1] for d in data])
  colors = ['limegreen'] * len(aindex)
  for pos, val in enumerate(aindex):
    if 20 < val < 30:
      colors[pos] = 'darkorange'
    elif 30 < val < 50:
      colors[pos] = 'red'
    elif 50 < val < 100:
      colors[pos] = 'darkred'
    elif val >= 100:
      colors[pos] = 'darkmagenta'

  today = datetime.utcnow().strftime('%Y/%m/%d %H:%M')
  fig = plt.figure(figsize=(12, 5))
  fig.suptitle('A-Index', fontsize=14, fontweight='bold')
  fig.text(0.01, 0.02, f'SunFluxBot By W6BSD {today}')
  fig.text(0.15, 0.8, "Forecast: " + data[-1][2], fontsize=12,
           bbox=dict(boxstyle='round', facecolor='grey', alpha=0.25, pad=.8))

  axgc = plt.gca()
  axgc.tick_params(labelsize=10)
  axgc.bar(datetm, aindex, linewidth=0.75, color=colors)

  loc = mdates.DayLocator(interval=4)
  axgc.xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d'))
  axgc.xaxis.set_major_locator(loc)
  axgc.xaxis.set_minor_locator(mdates.DayLocator())

  axgc.set_ylim(0, max(aindex) * 2)
  axgc.set_ylabel('A-Index')
  axgc.grid(color="gray", linestyle="dotted", linewidth=.5)
  axgc.margins(.01)

  fig.autofmt_xdate(rotation=10, ha="center")
  plt.savefig(filename, transparent=False, dpi=100)
  plt.close()
  logging.info('Graph "%s" saved', filename)
  return filename

def main():
  adapters.install_adapers()
  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s', datefmt='%H:%M:%S',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )
  config = Config()
  try:
    name = sys.argv[1]
  except IndexError:
    name = '/tmp/aindex.png'

  data = get_wwv(config, NB_DAYS)
  if data:
    graph(data, name)
  else:
    logging.warning('No data collected')

if __name__ == "__main__":
  sys.exit(main())
