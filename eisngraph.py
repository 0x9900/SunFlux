#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c) 2022-2023 Fred W6BSD
# All rights reserved.
#
#

import argparse
import csv
import logging
import os
import pickle
import sys
import time
from datetime import date, datetime, timezone
from urllib.request import urlopen

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from config import Config

plt.style.use(['classic', 'fast'])

logging.basicConfig(
  format='%(asctime)s %(levelname)s - %(name)s:%(lineno)3d - %(message)s', datefmt='%x %X',
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

  def graph(self, filenames):
    data = np.array(self.data)
    x = data[:, 0]
    y = data[:, 2].astype(np.float64)
    error = data[:, 3].astype(np.float64)
    vdata = data[:, 4].astype(np.float64)
    cdata = data[:, 5].astype(np.float64)

    today = datetime.now(timezone.utc).strftime('%Y/%m/%d %H:%M UTC')
    fig = plt.figure(figsize=(12, 5))
    fig.suptitle('Estimated International Sunspot Number (EISN)', fontsize=14, fontweight='bold')
    fig.text(0.01, 0.02, f'SunFluxBot By W6BSD {today}')
    axgc = plt.gca()
    axgc.tick_params(labelsize=10)
    axgc.plot(x, y, color="blue")
    axgc.axhline(y.mean(), color='red', linestyle='--', linewidth=1)
    axgc.plot(x, vdata, marker='*', linewidth=0, color='orange')
    axgc.plot(x, cdata, marker='.', linewidth=0, color='green')
    axgc.errorbar(x, y, yerr=error, fmt='*', color='green',
                  ecolor='darkolivegreen', elinewidth=.8, capsize=5,
                  capthick=.8)
    axgc.fill_between(x, y - error, y + error, facecolor='plum', alpha=1.0,
                      linewidth=.75, edgecolor='b')

    axgc.legend(['EISN', 'Average', 'Valid Data', 'Entries'], loc='best',
                fontsize="10", facecolor="linen", borderaxespad=1, ncol=2)

    loc = mdates.DayLocator(interval=int(1 + len(x) / 11))
    axgc.xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d UTC'))
    axgc.xaxis.set_major_locator(loc)
    axgc.xaxis.set_minor_locator(mdates.DayLocator())
    axgc.set_ylim(0, y.max() * 1.2)
    axgc.grid(color="gray", linestyle="dotted", linewidth=.5)
    axgc.margins(.01)
    fig.autofmt_xdate(rotation=10, ha="center")

    for filename in filenames:
      try:
        plt.savefig(filename, transparent=False, dpi=100)
        logger.info('Graph "%s" saved', filename)
      except ValueError as err:
        logger.error(err)
    plt.close()


def main():
  logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))
  config = Config().get('eisn', {})

  parser = argparse.ArgumentParser()
  parser.add_argument('-D', '--days', default=config.get('nb_days', NB_DAYS), type=int,
                      help='Number of days to graph [Default: %(default)s]')
  parser.add_argument('names', help='Name of the graph', nargs="*", default=['/tmp/eisn.png'])
  opts = parser.parse_args()

  cache_file = config.get('cache_file', '/tmp/eisn.pkl')
  cache_time = config.get('cache_time', 43200)
  eisn = EISN(cache_file, opts.days, cache_time)
  if not eisn.is_data():
    logger.warning('No data to graph')
    return os.EX_DATAERR

  eisn.graph(opts.names)
  return os.EX_OK


if __name__ == "__main__":
  sys.exit(main())
