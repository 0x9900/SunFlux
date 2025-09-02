#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c)2023-2025 Fred W6BSD
# All rights reserved.
#
#

import argparse
import json
import logging
import os
import pathlib
import pickle
import sys
import time
import urllib.request
import warnings
from datetime import datetime

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import ticker

import tools
from config import Config

warnings.filterwarnings('ignore')

logging.basicConfig(
  format='%(asctime)s %(levelname)s - %(name)s:%(lineno)3d - %(message)s', datefmt='%x %X',
  level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
)
logger = logging.getLogger('SolarWind')

NOAA_URL = 'https://services.swpc.noaa.gov/products/solar-wind/plasma-3-day.json'


def remove_outlier(points, low=25, high=95):
  percent_lo = np.percentile(points, low, interpolation='midpoint')
  percent_hi = np.percentile(points, high, interpolation='midpoint')
  iqr = percent_hi - percent_lo
  lower_bound = points <= (percent_lo - 5 * iqr)
  upper_bound = points >= (percent_hi + 5 * iqr)
  points[lower_bound | upper_bound] = np.nan
  return points


class SolarWind:
  def __init__(self, cache_file, cache_time=900):
    self.cachefile = cache_file
    self.data = None
    logger.debug('Import SolarWind')
    now = time.time()
    try:
      filest = os.stat(self.cachefile)
      if now - filest.st_mtime > cache_time:
        raise FileNotFoundError
    except FileNotFoundError:
      if self.download():
        self.writecache()
    self.readcache()

  def download(self):
    logger.info('Downloading data from NOAA')
    try:
      with urllib.request.urlopen(NOAA_URL) as res:
        webdata = res.read()
        encoding = res.info().get_content_charset('utf-8')
        _data = json.loads(webdata.decode(encoding))
    except (urllib.request.URLError, urllib.request.HTTPError) as err:
      logger.warning(err)
      return False
    except json.decoder.JSONDecodeError as err:
      logger.warning('JSon Decode Error: %s', err)
      return False

    data = []
    for elem in _data[1:]:
      date = datetime.strptime(elem[0], '%Y-%m-%d %H:%M:%S.%f')
      data.append([date, *[self.float(e) for e in elem[1:]]])
    self.data = np.array(sorted(data))
    self.data[:, 1] = remove_outlier(self.data[:, 1])
    return True

  def readcache(self):
    """Read data from the cache"""
    logger.debug('Read from cache "%s"', self.cachefile)
    try:
      with open(self.cachefile, 'rb') as fd_cache:
        data = pickle.load(fd_cache)
    except (FileNotFoundError, EOFError):
      data = None
    self.data = data

  def writecache(self):
    """Write data into the cachefile"""
    logger.debug('Write cache "%s"', self.cachefile)
    with open(self.cachefile, 'wb') as fd_cache:
      pickle.dump(self.data, fd_cache)

  @staticmethod
  def float(num):
    if num is None:
      return np.nan
    return float(num)

  def is_data(self):
    return bool(self.data.size)

  def graph(self, filename):
    # pylint: disable=too-many-locals
    colors = ["gray", "orange", "plum"]
    labels = {0: r"Density $1/cm^3$", 1: r"Speed $km/S$", 2: r"Temp $^{\circ}K$"}
    limits = {0: [0, 12], 1: [250, 750], 2: [10**3, 10**6]}
    fig, ax = plt.subplots(3, 1, figsize=(12, 5))
    fig.suptitle('Solar Wind (plasma)')

    formatter = ticker.ScalarFormatter(useMathText=True)
    formatter.set_scientific(True)
    formatter.set_useOffset(False)
    formatter.set_powerlimits((3, 6))
    loc = mdates.HourLocator(interval=6)

    for i in range(3):
      data = self.data[0:, i + 1].astype(np.float64)
      ax[i].plot(self.data[0:, 0], data, color=colors[i], linewidth=.5)
      ax[i].set_ylabel(labels[i], fontsize=8)
      if i in limits:
        _min, _max = limits[i]
        ax[i].axhline(_max, linewidth=0.5, zorder=5, color='red')
        _max = _max if np.nanmax(data) < _max else np.nanmax(data) * 1.1
        ax[i].set_ylim((_min, _max))
      if np.nanmean(data) > 10**3:
        ax[i].yaxis.set_major_formatter(formatter)
        offset_text = ax[i].yaxis.get_offset_text()
        offset_text.set_fontsize(8)
        offset_text.set_position((-0.04, 0))

      ax[i].tick_params(axis='both', which='major', labelsize=8)
      ax[i].xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %HH'))
      ax[i].xaxis.set_major_locator(loc)
      if i < 2:
        ax[i].tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)

    tools.save_plot(plt, filename)
    plt.close()


def main():
  config = Config().get('solarwind', {})
  cache_file = config.get('cache_file', '/tmp/solarwind.pkl')
  cache_time = config.get('cache_time', 900)
  target_dir = config.get('target_dir', '/var/www/html')

  parser = argparse.ArgumentParser()
  parser.add_argument('-t', '--target', type=pathlib.Path, default=target_dir,
                      help='Image path')
  opts = parser.parse_args()

  wind = SolarWind(cache_file, cache_time)
  if not wind.is_data():
    logger.error('No data to plot')
    return os.EX_DATAERR

  styles = tools.STYLES
  for style in styles:
    with plt.style.context(style.style):
      filename = opts.target.joinpath(f'solarwind-{style.name}')
      wind.graph(filename)
      if style.name == 'light':
        tools.mk_link(filename, opts.target.joinpath('solarwind'))
  return os.EX_OK


if __name__ == "__main__":
  sys.exit(main())
