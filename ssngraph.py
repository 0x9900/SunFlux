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
import pickle
import sys
import time
from datetime import date
from itertools import cycle
from urllib.request import urlopen

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MultipleLocator

import tools
from config import Config

logging.basicConfig(
  format='%(asctime)s %(levelname)s - %(name)s:%(lineno)3d - %(message)s', datefmt='%x %X',
  level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
)
logger = logging.getLogger('SSN')

NOAA_URL = 'https://services.swpc.noaa.gov/text/daily-solar-indices.txt'


def moving_average(data, window=5):
  average = np.convolve(data, np.ones(window), 'valid') / window
  for _ in range(window - 1):
    average = np.insert(average, 0, np.nan)
  return average


class SSN:
  def __init__(self, cache_file, cache_time=43200):
    self.log = logging.getLogger('SSN')
    self.data = SSN.read_cache(cache_file)

    if SSN.is_expired(cache_file, cache_time):
      self.log.info('Downloading data from NOAA')
      self.data = SSN.read_url(NOAA_URL, self.data)
      SSN.write_cache(cache_file, self.data)

    self.data = self.data[-90:]

  @staticmethod
  def read_url(url, current_data):
    with urlopen(url) as resp:
      if resp.status != 200:
        return current_data
      charset = resp.info().get_content_charset('utf-8')
      data = current_data
      for line in resp:
        line = line.decode(charset).strip()
        if not line or line[0] in ('#', ':'):
          continue
        data.append(SSN.convert(line))

    # de-dup
    _data = {v[0]: v for v in data}
    return sorted(_data.values())

  @staticmethod
  def convert(line):
    #                         Sunspot       Stanford GOES15
    #           Radio  SESC     Area          Solar  X-Ray  ------ Flares ------
    #           Flux  Sunspot  10E-6   New     Mean  Bkgd    X-Ray      Optical
    #  Date     10.7cm Number  Hemis. Regions Field  Flux   C  M  X  S  1  2  3
    fields = line.split()[:6]
    fields = [int(f) for f in fields]
    return (date(*fields[:3]), *fields[3:])

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

  def graph(self, filename, style):
    # pylint: disable=too-many-locals
    data = np.array(self.data)

    xtime = data[:, 0]
    ssn = data[:, 2]
    flux = data[:, 1]
    avg = moving_average(ssn)

    fig = plt.figure(figsize=(12, 5))
    fig.suptitle('Sunspot Number (SSN)')
    axgc = plt.gca()
    axgc.plot(xtime, ssn, label="Sun spot", marker='o', markersize=4, linewidth=1)
    axgc.plot(xtime, avg, label="5day average", linewidth=2, zorder=5)
    axgc.plot(xtime, flux, label="10.7cm Flux", linestyle='-.', linewidth=1)
    loc = mdates.DayLocator(interval=int(1 + len(xtime) / 11))
    axgc.xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d UTC'))
    axgc.xaxis.set_major_locator(loc)
    axgc.xaxis.set_minor_locator(mdates.DayLocator())
    axgc.yaxis.set_major_locator(MultipleLocator(50))
    axgc.set_ylabel('Sun Sport Number')

    axgc.set_ylim(np.min([ssn, flux]) * 0.2, np.max([ssn, flux]) * 1.15)
    axgc.minorticks_on()

    sign = cycle([-1, 1])
    for _x, _y, _s in zip(xtime, ssn, sign):
      plt.annotate(f"{_y:d}", (_x, _y), textcoords="offset points", xytext=(0, 20 * _s),
                   ha='center', fontsize=8, color=style.top,
                   arrowprops={"arrowstyle": "->", "color": style.top})

    axgc.legend()
    fig.autofmt_xdate(rotation=10, ha="center")

    tools.save_plot(plt, filename)
    plt.close()


def main():
  config = Config().get('ssngraph', {})
  cache_file = config.get('cache_file', '/tmp/ssn.pkl')
  cache_time = config.get('cache_time', 43200)
  target_dir = config.get('target_dir', '/var/www/html')

  parser = argparse.ArgumentParser()
  parser.add_argument('-t', '--target', type=pathlib.Path, default=target_dir,
                      help='Image path')
  opts = parser.parse_args()

  ssn = SSN(cache_file, cache_time)
  if not ssn.is_data():
    logger.error('No data to graph')
    return os.EX_DATAERR

  for style in tools.STYLES:
    with plt.style.context(style.style):
      filename = opts.target.joinpath(f'ssn-{style.name}')
      ssn.graph(filename, style)
      if style.name == 'light':
        tools.mk_link(filename, opts.target.joinpath('ssn'))

  return os.EX_OK


if __name__ == "__main__":
  sys.exit(main())
