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
import pathlib
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from itertools import product

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter

import adapters
import tools
from config import Config

adapters.install_adapters()

DPI = 100
NB_DAYS = 15

SQL_REQ = """SELECT STRFTIME("%Y%m%d", DATETIME(time, "unixepoch")) AS tm, mode, COUNT(*) AS cnt
             FROM dxspot WHERE time > {} GROUP BY mode, tm"""

logging.basicConfig(
  format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s', datefmt='%x %X',
  level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
)
logger = logging.getLogger('graphmodes')


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


def sizeof_fmt(num, _):
  for unit in ("", "K", "M"):
    if abs(num) < 1000.0:
      return f"{num:.0f}{unit}"
    num /= 1024.0
  return f"{num:.1f}"


def graph(data, filename):
  xdate = np.array(list(data.keys()))
  modes = sorted({k for d in data.values() for k in d})
  ydata = defaultdict(list)
  for val, mode in product(data.values(), modes):
    try:
      ydata[mode].append(val[mode])
    except KeyError:
      ydata[mode].append(0)

  fig, ax1 = plt.subplots(figsize=(12, 5))
  fig.suptitle('Band Activity / Modes')
  ax1.set_ylabel('Sports / Day')
  ax1.margins(x=0.01, y=0.02)
  prev = np.zeros(len(xdate))
  for mode in modes:
    value = np.array(ydata[mode], dtype=float)
    ax1.bar(xdate, value, label=mode, bottom=prev, alpha=.8, zorder=10)
    prev += value

  _, ymax = ax1.get_ylim()
  ax1.set_ylim((0, ymax + ymax*.10))
  ax1.yaxis.set_major_formatter(FuncFormatter(sizeof_fmt))
  ax1.legend(loc='upper left')
  fig.autofmt_xdate(rotation=10, ha="center")
  tools.save_plot(plt, filename)


def main():
  try:
    _config = Config()
    config = _config['graphmode']
    del _config
  except KeyError as err:
    logger.error(err)
    return os.EX_CONFIG

  target_dir = config.get('target_dir', '/var/www/html')

  parser = argparse.ArgumentParser()
  parser.add_argument('-D', '--days', default=NB_DAYS, type=int,
                      help='Number of days to graph [Default: %(default)s]')
  parser.add_argument('-t', '--target', type=pathlib.Path, default=target_dir,
                      help='Image path')
  opts = parser.parse_args()

  data = read_data(config, opts.days)
  styles = tools.STYLES
  for style in styles:
    with plt.style.context(style.style):
      filename = opts.target.joinpath(f'modes-{opts.days}-{style.name}')
      graph(data, filename)
      if style.name == 'light' and opts.days == 15:
        tools.mk_link(filename, opts.target.joinpath('modes'))

  return os.EX_OK


if __name__ == "__main__":
  main()
