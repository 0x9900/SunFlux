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
import re
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

NOAA_URL = 'https://services.swpc.noaa.gov/json/goes/primary/integral-protons-3-day.json'

def noaa_date(dct):
  date = datetime.strptime(dct['time_tag'], '%Y-%m-%dT%H:%M:%SZ')
  dct['time_tag'] = date
  return dct

def remove_outlier(points):
  percent_lo = np.percentile(points, 25, interpolation = 'midpoint')
  percent_hi= np.percentile(points, 95, interpolation = 'midpoint')
  iqr = percent_hi - percent_lo
  lower_bound = points <= (percent_lo - 5 * iqr)
  upper_bound = points >= (percent_hi + 5 * iqr)
  points[lower_bound | upper_bound] = np.nan
  return points

class ProtonFlux:
  def __init__(self, cache_file, cache_time=900):
    self.log = logging.getLogger('ProtonFlux')
    self.cachefile = cache_file
    self.data = None
    self.log.debug('Import Proton Flux')
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
    _re = re.compile(r'>=(\d+)\sMeV')

    def get_e(field):
      if match := _re.match(field):
        return match.group(1)
      return None

    with urllib.request.urlopen(NOAA_URL) as res:
      webdata = res.read()
      encoding = res.info().get_content_charset('utf-8')
      _data = json.loads(webdata.decode(encoding), object_hook=noaa_date)

    data = {}
    for elem in _data:
      data[elem['time_tag']] = {k: 0.0 for k in (1, 10, 100, 30, 5, 50, 500, 60)}

    for elem in _data:
      date = elem['time_tag']
      energy = int(get_e(elem['energy']))
      data[date][energy] = elem['flux']
    self.data = data

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
    energy = (10, 30, 50, 100)  # Graphs to plot
    colors = {10: "tab:orange", 30: "tab:olive", 50: "tab:blue", 100: "tab:cyan"}
    fig = plt.figure(figsize=(12, 5))
    fig.subplots_adjust(bottom=0.15)

    fig.suptitle('Proton Flux', fontsize=14, fontweight='bold')
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

    dates  = np.array(list(self.data.keys()))

    _max = 0
    for _energy in energy:
      data = np.array([flux[_energy] for flux in self.data.values()])
      data = remove_outlier(data)
      ax.plot(dates, data, linewidth=1.25, color=colors[_energy], zorder=2,
              label=f'>={_energy} MeV')
      _max = max(data.max(), _max)

    magnitude = 1 + int(math.log(_max, 10))
    ax.set_ylim((0.1, 10**magnitude))

    if magnitude > 100:
      ax.axhline(100, linewidth=1, linestyle="--", zorder=0, color='tab:red',
                 label='Warning Threshold')

    legend = ax.legend(loc='best', fontsize="12", facecolor="linen",
                       borderpad=1.25, borderaxespad=1)
    for line in legend.get_lines():
      if line.get_label().startswith('>'):
        line.set_linewidth(5.0)
      else:
        line.set_linewidth(2)

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
    name = '/tmp/proton_flux.png'

  cache_file = config.get('protonflux.cache_file', '/tmp/proton_flux.pkl')
  cache_time = config.get('protonflux.cache_time', 3600)
  p_f = ProtonFlux(cache_file, cache_time)
  if not p_f.graph(name):
    return os.EX_DATAERR

  return os.EX_OK

if __name__ == "__main__":
  sys.exit(main())
