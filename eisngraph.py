#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c)2022-2023 Fred W6BSD
# All rights reserved.
#
#

import argparse
import csv
import logging
import os
import pathlib
import pickle
import sys
import time
from datetime import date
from itertools import cycle
from urllib.request import urlopen

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

import tools
from config import Config

logging.basicConfig(
  format='%(asctime)s %(levelname)s - %(name)s:%(lineno)3d - %(message)s', datefmt='%x %X',
  level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
)
logger = logging.getLogger('EISN')

SIDC_URL = 'https://www.sidc.be/silso/DATA/EISN/EISN_current.csv'
NB_DAYS = 90


class EISN:
  def __init__(self, cache_file, days=NB_DAYS, cache_time=43200):
    data = EISN.read_cache(cache_file)
    if EISN.is_expired(cache_file, cache_time):
      logger.info('Downloading data from SIDC')
      data = EISN.read_url(SIDC_URL, data)
      EISN.write_cache(cache_file, data)
    days = abs(days) * -1			# making sure we have a negative number
    self.data = data[days:]

  @staticmethod
  def read_url(url, current_data):
    with urlopen(url) as resp:
      if resp.status != 200:
        return current_data
      charset = resp.info().get_content_charset('utf-8')
      csvfd = csv.reader(r.decode(charset) for r in resp)
      data = current_data
      for fields in csvfd:
        data.append(EISN.convert(fields))

    # de-dup
    _data = {v[0]: v for v in data}
    return sorted(_data.values())[-90:]

  @staticmethod
  def convert(fields):
    ftmp = []
    for field in fields:
      field = field.strip()
      if str.isdecimal(field):
        ftmp.append(int(field))
      elif '.' in field:
        ftmp.append(float(field))
      else:
        ftmp.append(0)
    day = dict(zip(['year', 'month', 'day'], ftmp[:3]))
    return tuple([date(**day)] + ftmp[3:])

  @staticmethod
  def read_cache(cache_file):
    try:
      with open(cache_file, 'rb') as cfd:
        return pickle.load(cfd)
    except (FileNotFoundError, EOFError):
      return []

  @staticmethod
  def write_cache(cache_file, data):
    with open(cache_file, 'wb') as cfd:
      pickle.dump(data, cfd)

  @staticmethod
  def is_expired(cache_file, cache_time):
    now = time.time()
    try:
      filest = os.stat(cache_file)
      if now - filest.st_mtime > cache_time:
        return True
    except FileNotFoundError:
      return True
    return False

  def is_data(self):
    return bool(self.data)

  @staticmethod
  def anotate(xtime, ssn, style):
    sign = cycle([-1, 1])
    for _x, _y, _s in zip(xtime, ssn, sign):
      if _s == 0:
        continue
      plt.annotate(f"{int(_y):d}", (_x, _y), textcoords="offset points", xytext=(0, 20 * _s),
                   ha='center', fontsize=8, color=style.top,
                   arrowprops={"arrowstyle": "->", "color": style.top})

  def graph(self, filename, style):
    data = np.array(self.data)
    x = data[:, 0]
    y = data[:, 2].astype(np.float64)
    error = data[:, 3].astype(np.float64)
    vdata = data[:, 4].astype(np.float64)
    cdata = data[:, 5].astype(np.float64)

    fig = plt.figure(figsize=(12, 5))
    fig.suptitle('Estimated International Sunspot Number (EISN)')
    axgc = plt.gca()
    axgc.tick_params(labelsize=10)
    axgc.plot(x, y, label='Sun Spot', linewidth=1.5)
    axgc.fill_between(x, y - error, y + error, alpha=.2, linewidth=.75, edgecolor='g',
                      label="Estimated")
    axgc.plot(x, cdata, marker='2', linewidth=0, color=style.bottom, label='Nb. entries')
    axgc.plot(x, vdata, marker='1', linewidth=0, color=style.top, label='Valid entries')

    axgc.legend(ncol=2)

    loc = mdates.DayLocator(interval=int(1 + len(x) / 11))
    axgc.xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d'))
    axgc.xaxis.set_major_locator(loc)
    axgc.xaxis.set_minor_locator(mdates.DayLocator())
    axgc.set_ylim(0, y.max() * 1.2)
    fig.autofmt_xdate(rotation=10, ha="center")
    self.anotate(x, y, style)

    tools.save_plot(plt, filename)
    plt.close()


def main():
  config = Config().get('eisn', {})
  target_dir = config.get('target_dir', '/var/www/html')
  cache_file = config.get('cache_file', '/tmp/eisn.pkl')
  cache_time = config.get('cache_time', 43200)

  parser = argparse.ArgumentParser()
  parser.add_argument('-D', '--days', default=config.get('nb_days', NB_DAYS), type=int,
                      help='Number of days to graph [Default: %(default)s]')
  parser.add_argument('-t', '--target', type=pathlib.Path, default=target_dir,
                      help='Image path')
  opts = parser.parse_args()

  eisn = EISN(cache_file, opts.days, cache_time)
  if not eisn.is_data():
    logger.warning('No data to graph')
    return os.EX_DATAERR

  styles = tools.STYLES
  for style in styles:
    with plt.style.context(style.style):
      filename = opts.target.joinpath(f'eisn-{style.name}')
      eisn.graph(filename, style)
      if style.name == 'light':
        tools.mk_link(filename, opts.target.joinpath('eisn'))
  return os.EX_OK


if __name__ == "__main__":
  sys.exit(main())
