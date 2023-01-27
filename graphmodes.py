#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c) 2022 Fred W6BSD
# All rights reserved.
#
#

import logging
import os
import pickle
import sqlite3
import sys
import time

from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps

import matplotlib.pyplot as plt
import numpy as np

import adapters

from config import Config

adapters.install_adapters()

plt.style.use(['classic', 'tableau-colorblind10'])

TMPDIR = '/tmp'
DPI = 100

SQL_REQ = """SELECT STRFTIME("%Y%m%d", DATETIME(time, "unixepoch")) AS tm, mode, COUNT(*) AS cnt
             FROM dxspot GROUP BY mode, tm"""

def read_data(config):
  data = defaultdict(dict)
  conn = sqlite3.connect(
    config['db_name'],
    timeout=5,
    detect_types=sqlite3.PARSE_DECLTYPES
  )
  today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
  today = today - timedelta(hours=24)
  start = today - timedelta(hours=24*15)
  with conn:
    curs = conn.cursor()
    results = curs.execute(SQL_REQ)
    for date, mode, count in results:
      date = datetime.strptime(date, '%Y%m%d')
      if not start < date <= today:
        continue
      if mode is None:
        mode = 'SSB'
      elif mode.startswith('PSK') or mode == 'RTTY':
        mode = 'DIGI'
      data[date].setdefault(mode, 0)
      data[date][mode] += int(count)
  return data


def graph(data, imgname):
  now = datetime.utcnow().strftime('%Y/%m/%d %H:%M')
  xdate = np.array(list(data.keys()))
  modes = sorted({k for d in data.values() for k in d})
  ydata = defaultdict(list)
  for val in data.values():
    for mode in modes:
      try:
        ydata[mode].append(val[mode])
      except KeyError:
        ydata[mode].append(0)

  fig, ax1 = plt.subplots(figsize=(12, 5))
  fig.suptitle('Number of Spots / Modes', fontsize=14, fontweight='bold')
  fig.text(0.01, 0.02, f'SunFluxBot By W6BSD {now}')
  ax1.set_xlabel('Date', fontsize=12, fontweight='bold')
  ax1.set_ylabel('Sports / Day', fontsize=12, fontweight='bold')
  ax1.margins(x=0.01, y=0.02)
  colors = plt.cm.Set2(np.linspace(0, 1, len(modes)))
  colors[0] = (1,.5,0,1)
  prev = np.zeros(len(xdate))
  for idx, mode in enumerate(modes):
    value = np.array(ydata[mode], dtype=float)
    ax1.bar(xdate, value, label=mode, bottom=prev, color=colors[idx])
    prev += 3000
    prev += value

  ax1.legend(loc='upper left', fontsize=10)
  graphname = os.path.join(TMPDIR, imgname)
  fig.autofmt_xdate(rotation=10, ha="center")
  plt.savefig(graphname, transparent=False, dpi=DPI)
  logging.info('Generate graph: %s', graphname)


def main():
  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s', datefmt='%H:%M:%S',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )
  _config = Config()
  config = _config.get('dxcluster')
  del _config

  try:
    name = sys.argv[1]
  except IndexError:
    name = '/tmp/modes.png'

  data = read_data(config)
  graph(data, name)

if __name__ == "__main__":
  main()
