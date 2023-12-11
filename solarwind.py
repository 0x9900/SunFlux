#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c) 2023 Fred W6BSD
# All rights reserved.
#
#

import argparse
import json
import logging
import os
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

from config import Config

# Older versions of numpy are too verbose when arrays contain np.nan values
# This 2 lines will have to be removed in future versions of numpy
warnings.filterwarnings('ignore')

logging.basicConfig(
  format='%(asctime)s %(levelname)s - %(name)s:%(lineno)3d - %(message)s', datefmt='%x %X',
)
logger = logging.getLogger('SolarWind')

plt.style.use(['classic', 'fast'])

NOAA_URL = 'https://services.swpc.noaa.gov/products/solar-wind/plasma-3-day.json'

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
      self.download()
      self.writecache()
    else:
      self.readcache()

  def download(self):
    logger.info('Downloading data from NOAA')
    with urllib.request.urlopen(NOAA_URL) as res:
      webdata = res.read()
      encoding = res.info().get_content_charset('utf-8')
      _data = json.loads(webdata.decode(encoding))

    data = []
    for elem in _data[1:]:
      date = datetime.strptime(elem[0], '%Y-%m-%d %H:%M:%S.%f')
      data.append([date, *[self.float(e) for e in elem[1:]]])
    self.data = np.array(sorted(data))

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

  def graph(self, image_names):
    # pylint: disable=too-many-locals
    colors = {0: "gray", 1: "orange", 2: "plum"}
    labels = {0: r"Density $1/cm^3$", 1: r"Speed $km/S$", 2: r"Temp $^{\circ}K$"}
    limits = {0: [0, 12], 1: [250, 750]} #,  2: [10**3, 10**6]}
    fig, ax = plt.subplots(3, 1, figsize=(12, 5))
    fig.suptitle('Solar Wind (plasma)', fontsize=14, fontweight='bold')

    formatter = ticker.ScalarFormatter(useMathText=True)
    formatter.set_scientific(True)
    formatter.set_powerlimits((-1,1))
    loc = mdates.HourLocator(interval=6)

    for i in range(3):
      data = self.data[0:,i+1]
      ax[i].plot(self.data[0:,0], data, color=colors[i], linewidth=.5,
                 marker='.', markersize=.5)
      ax[i].grid(color='tab:gray', linestyle='dotted', linewidth=.3)
      ax[i].set_ylabel(labels[i], fontsize=10)
      if i in limits:
        _min, _max = limits[i]
        ax[i].axhline(_max, linewidth=1, zorder=1, color='lightgray')
        _max = _max if np.max(data) < _max else np.max(data) * 1.10
        ax[i].set_ylim((_min, _max))
      ax[i].yaxis.offsetText.set_fontsize(10)
      if np.min(data) > 1000:
        ax[i].yaxis.set_major_formatter(formatter)
      ax[i].tick_params(axis='y', labelsize=8)
      ax[i].tick_params(axis='x', labelsize=9)
      ax[i].xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %HH'))
      ax[i].xaxis.set_major_locator(loc)

    today = datetime.utcnow().strftime('%Y/%m/%d %H:%M UTC')
    plt.figtext(0.01, 0.02, f'SunFluxBot By W6BSD {today}', fontsize=10)
    for name in image_names:
      try:
        fig.savefig(name, transparent=False, dpi=100)
        logger.info('Save "%s"', name)
      except ValueError as err:
        logger.error(err)
    plt.close()


def main():
  logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))
  config = Config().get('solarwind', {})

  parser = argparse.ArgumentParser()
  parser.add_argument('names', help='Name of the graph', nargs="*",
                      default=['/tmp/solarwind.png'])
  opts = parser.parse_args()

  cache_file = config.get('cache_file', '/tmp/solarwind.pkl')
  cache_time = config.get('cache_time', 900)
  wind = SolarWind(cache_file, cache_time)
  if not wind.is_data():
    logger.error('No data to plot')
    return os.EX_DATAERR

  wind.graph(opts.names)
  return os.EX_OK

if __name__ == "__main__":
  sys.exit(main())
