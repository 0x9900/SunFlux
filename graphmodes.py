#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c)2022-2023 Fred W6BSD
# All rights reserved.
#
#

import argparse
import logging
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from itertools import product

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm

import adapters
from config import Config

adapters.install_adapters()

plt.style.use(['classic', 'tableau-colorblind10'])

DPI = 100
NB_DAYS = 15

SQL_REQ = """SELECT STRFTIME("%Y%m%d", DATETIME(time, "unixepoch")) AS tm, mode, COUNT(*) AS cnt
             FROM dxspot WHERE time > {} GROUP BY mode, tm"""


def read_data(config, days=15):
  data = defaultdict(dict)
  conn = sqlite3.connect(
    config['db_name'],
    timeout=5,
    detect_types=sqlite3.PARSE_DECLTYPES
  )
  today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  today -= timedelta(hours=24)
  start = today - timedelta(hours=24 * days)
  with conn:
    curs = conn.cursor()
    results = curs.execute(SQL_REQ.format(start.timestamp(),))
    for date, mode, count in results:
      date = datetime.strptime(date, '%Y%m%d')
      date = date.replace(tzinfo=timezone.utc)
      if not start < date <= today:
        continue
      if mode is None:
        mode = 'SSB'
      elif mode.startswith('PSK') or mode == 'RTTY':
        mode = 'DIGI'
      data[date].setdefault(mode, 0)
      data[date][mode] += int(count)
  return data


def graph(data, imgnames):
  now = datetime.now(timezone.utc).strftime('%Y/%m/%d %H:%M %Z')
  xdate = np.array(list(data.keys()))
  modes = sorted({k for d in data.values() for k in d})
  ydata = defaultdict(list)
  for val, mode in product(data.values(), modes):
    try:
      ydata[mode].append(val[mode])
    except KeyError:
      ydata[mode].append(0)

  fig, ax1 = plt.subplots(figsize=(12, 5))
  fig.suptitle('Band Activity / Modes', fontsize=14, fontweight='bold')
  fig.text(0.01, 0.02, f'SunFlux (c)W6BSD {now}', fontsize=8, style='italic')
  ax1.set_ylabel('Sports / Day', fontsize=12)
  ax1.margins(x=0.01, y=0.02)
  colors = cm.Set2(np.linspace(0, 1, len(modes)))  # pylint: disable=no-member
  colors[0] = (1, .5, 0, 1)
  prev = np.zeros(len(xdate))
  for idx, mode in enumerate(modes):
    value = np.array(ydata[mode], dtype=float)
    ax1.bar(xdate, value, label=mode, bottom=prev, color=colors[idx])
    prev += 3000
    prev += value

  ax1.legend(loc='upper left', fontsize=10)
  fig.autofmt_xdate(rotation=10, ha="center")
  for graphname in imgnames:
    plt.savefig(graphname, transparent=False, dpi=DPI)
    logging.info('Generate graph: %s', graphname)


def main():
  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s', datefmt='%x %X',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )
  parser = argparse.ArgumentParser()
  parser.add_argument('-D', '--days', default=NB_DAYS, type=int,
                      help='Number of days to graph [Default: %(default)s]')
  parser.add_argument('graph_names', help='Name of the graphs', nargs="*",
                      default=['/tmp/modes.png'])
  opts = parser.parse_args()

  try:
    _config = Config()
    config = _config['graphmode']
    del _config
  except KeyError as err:
    logging.error(err)
    return os.EX_CONFIG

  data = read_data(config, opts.days)
  graph(data, opts.graph_names)
  return os.EX_OK


if __name__ == "__main__":
  main()
