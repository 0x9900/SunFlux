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
SELECT MAX(wwv.A), DATE(DATETIME(wwv.time, "unixepoch")) AS dt
FROM wwv
WHERE wwv.time > ?
GROUP BY dt
"""

WWV_CONDITIONS = "SELECT conditions FROM wwv ORDER BY time DESC LIMIT 1"

def get_conditions(config):
  conn = sqlite3.connect(config['showdxcc.db_name'], timeout=5,
                         detect_types=sqlite3.PARSE_DECLTYPES)
  with conn:
    curs = conn.cursor()
    result = curs.execute(WWV_CONDITIONS).fetchone()
  return result[0]

def get_wwv(config, days):
  data = []
  start_date = datetime.utcnow() - timedelta(days=days)
  conn = sqlite3.connect(config['showdxcc.db_name'], timeout=5,
                         detect_types=sqlite3.PARSE_DECLTYPES)
  with conn:
    curs = conn.cursor()
    results = curs.execute(WWV_REQUEST, (start_date,))
    for res in results:
      dte = datetime.strptime(res[1], '%Y-%m-%d')
      data.append((dte, res[0]))
  return data

def autolabel(ax, rects):
  """Attach a text label above each bar displaying its height"""
  for rect in rects:
    height = rect.get_height()
    ax.text(rect.get_x() + rect.get_width() / 2., 3, '%d' % int(height),
            color="navy", fontsize="6", ha='center',
            bbox={"facecolor": 'white', "alpha": .9})

def graph(data, condition, filename):

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
  fig.text(0.15, 0.8, "Forecast: " + condition, fontsize=12,
           bbox=dict(boxstyle='round', facecolor='grey', alpha=0.25, pad=.8))

  axgc = plt.gca()
  axgc.tick_params(labelsize=10)
  bars = axgc.bar(datetm, aindex, linewidth=0.75, zorder=2, color=colors)
  autolabel(axgc, bars)

  axgc.axhline(y=20, linewidth=1, zorder=1, color='green', linestyle="dashed")
  axgc.axhline(y=30, linewidth=1, zorder=1, color='darkorange', linestyle="dashed")
  axgc.axhline(y=40, linewidth=1, zorder=1, color='red', linestyle="dashed")
  axgc.axhline(y=50, linewidth=1, zorder=1, color='darkred', linestyle="dashed")
  axgc.axhline(y=100, linewidth=1, zorder=1, color='darkmagenta', linestyle="dashed")

  loc = mdates.DayLocator(interval=4)
  axgc.xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d'))
  axgc.xaxis.set_major_locator(loc)
  axgc.xaxis.set_minor_locator(mdates.DayLocator())

  axgc.set_ylim(0, max(aindex) * (2 if max(aindex) < 50 else 1.25))
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
  condition = get_conditions(config)
  if data:
    graph(data, condition, name)
  else:
    logging.warning('No data collected')


if __name__ == "__main__":
  sys.exit(main())
