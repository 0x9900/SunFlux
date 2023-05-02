#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c) 2023 Fred W6BSD
# All rights reserved.
#
#

import json
import logging
import os
import pickle
import sys
import time
import urllib.request

from datetime import datetime, timedelta

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from matplotlib import ticker

from config import Config

NOAA_URL = 'https://services.swpc.noaa.gov/products/solar-wind/plasma-3-day.json'

plt.style.use(['classic', 'fast'])

class SolarWind:
  def __init__(self, cache_file, cache_time=900):
    self.log = logging.getLogger('SolarWind')
    self.cachefile = cache_file
    self.data = None
    self.log.debug('Import SolarWind')
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
    self.log.info('Downloading data from NOAA')
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
    self.log.debug('Read from cache "%s"', self.cachefile)
    try:
      with open(self.cachefile, 'rb') as fd_cache:
        data = pickle.load(fd_cache)
    except (FileNotFoundError, EOFError):
      data = None
    self.data = data

  def writecache(self):
    """Write data into the cachefile"""
    self.log.debug('Write cache "%s"', self.cachefile)
    with open(self.cachefile, 'wb') as fd_cache:
      pickle.dump(self.data, fd_cache)

  @staticmethod
  def float(num):
    if num is None:
      return None
    return float(num)

  def graph(self, imagename):
    colors = {0: "gray", 1: "orange", 2: "plum"}
    labels = {0: "Density $1/cm^3$", 1: "Speed $km/S$", 2: "Temp $^{\circ}K$"}

    fig, ax = plt.subplots(3, 1, figsize=(12, 5))
    fig.suptitle('Solar Wind (plasma)', fontsize=14, fontweight='bold')

    formatter = ticker.ScalarFormatter(useMathText=True)
    formatter.set_scientific(True)
    formatter.set_powerlimits((-1,1))
    loc = mdates.HourLocator(interval=12)

    for i in range(3):
      ax[i].plot(self.data[0:,0], self.data[0:,i+1], color=colors[i], linewidth=.5,
                 marker='.', markersize=.5)
      ax[i].grid(color='darkgray', linestyle='-', linewidth=.2)
      ax[i].set_ylabel(labels[i], fontsize=10)
      ax[i].yaxis.offsetText.set_fontsize(10)
      if np.min(self.data[0:,i+1]) > 1000:
        ax[i].yaxis.set_major_formatter(formatter)
      ax[i].tick_params(axis='y', labelsize=8)
      ax[i].tick_params(axis='x', labelsize=10)
      if i < 2:
        ax[i].xaxis.set_major_formatter(plt.NullFormatter())
        continue
      ax[i].xaxis.set_major_formatter(mdates.DateFormatter('%d/%H:%M'))
      ax[i].xaxis.set_major_locator(loc)

    date = datetime.utcnow()
    plt.figtext(0.01, 0.02, f'SunFluxBot By W6BSD {date}', fontsize=11)
    self.log.info('Save "%s"', imagename)
    fig.savefig(imagename, transparent=False, dpi=100)
    plt.close()


def main():
  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)3d - %(levelname)s - %(message)s', datefmt='%H:%M:%S',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )
  config = Config()
  try:
    name = sys.argv[1]
  except IndexError:
    name = '/tmp/solarwind.png'

  cache_file = config.get('solarwind.cache_file', '/tmp/solarwind.pkl')
  cache_time = config.get('solarwind.cache_time', 900)
  wind = SolarWind(cache_file, cache_time)
  wind.graph(name)
  return os.EX_OK

if __name__ == "__main__":
  sys.exit(main())
