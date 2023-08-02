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
import math
import os
import pickle
import sys
import time
import urllib.request

from datetime import datetime

import warnings

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from matplotlib import ticker

from config import Config

# Older versions of numpy are too verbose when arrays contain np.nan values
# This 2 lines will have to be removed in future versions of numpy
warnings.filterwarnings('ignore')

NOAA_URL = 'https://services.swpc.noaa.gov/json/goes/primary/xrays-3-day.json'

def noaa_date(dct):
  date = datetime.strptime(dct['time_tag'], '%Y-%m-%dT%H:%M:%SZ')
  dct['time_tag'] = date
  return dct

def remove_outlier(points, low=25, high=95):
  percent_lo = np.percentile(points, low, interpolation = 'midpoint')
  percent_hi= np.percentile(points, high, interpolation = 'midpoint')
  iqr = percent_hi - percent_lo
  lower_bound = points <= (percent_lo - 5 * iqr)
  upper_bound = points >= (percent_hi + 5 * iqr)
  points[lower_bound | upper_bound] = np.nan
  return points

class XRayFlux:
  def __init__(self, cache_file, cache_time=900):
    self.log = logging.getLogger("XRayFlux")
    self.cachefile = cache_file
    self.data = None
    self.log.debug('Import XRay Flux')
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
    self.log.info('Downloading XRayFlux data from NOAA')

    with urllib.request.urlopen(NOAA_URL) as res:
      webdata = res.read()
      encoding = res.info().get_content_charset('utf-8')
      _data = json.loads(webdata.decode(encoding), object_hook=noaa_date)
    self.data = {e['time_tag']: e for e in _data}

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

  def graph(self, imagename):
    dates  = np.array(list(self.data.keys()))
    data = np.array([d['flux'] for d in self.data.values()])
    data = remove_outlier(data)

    fig = plt.figure(figsize=(12, 5))
    fig.subplots_adjust(bottom=0.15)

    fig.suptitle('XRay Flux', fontsize=14, fontweight='bold')
    ax = plt.gca()
    ax.set_yscale("log")
    ax.tick_params(axis='x', which='both', labelsize=12, rotation=10)

    formatter = ticker.ScalarFormatter(useMathText=True)
    formatter.set_scientific(True)
    formatter.set_powerlimits((-1,1))
    ax.grid(color='brown', linestyle='dotted', linewidth=.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%H:%M'))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=12))
    ax.xaxis.set_minor_locator(mdates.HourLocator())

    max_mag = int(math.log(data[data>0.0].max(), 10)) + 1
    min_mag = int(math.log(data[data>0.0].min(), 10)) - 1
    ax.set_ylim((10**min_mag, 10**max_mag))

    data[data==0.0] = np.nan
    ax.plot(dates, data, linewidth=1.5, color="tab:blue", zorder=2,
            label='Flux')

    ax.legend(loc='best', fontsize="12", facecolor="linen",
                       borderpad=1, borderaxespad=1)
    today = datetime.utcnow().strftime('%Y/%m/%d %H:%M UTC')
    plt.figtext(0.01, 0.02, f'SunFluxBot By W6BSD {today}', fontsize=12)
    fig.savefig(imagename, transparent=False, dpi=100)
    plt.close()
    self.log.info('Saved "%s"', imagename)


def main():
  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)3d - %(levelname)s - %(message)s', datefmt='%H:%M:%S',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )
  config = Config()
  try:
    name = sys.argv[1]
  except IndexError:
    name = '/tmp/xray_flux.png'

  cache_file = config.get('xrayflux.cache_file', '/tmp/xrayflux.pkl')
  cache_time = config.get('xrayflux.cache_time', 3600)
  xray = XRayFlux(cache_file, cache_time)
  xray.graph(name)

if __name__ == "__main__":
  sys.exit(main())
