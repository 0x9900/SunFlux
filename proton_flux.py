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
from tools import noaa_date_hook
from tools import remove_outliers

# Older versions of numpy are too verbose when arrays contain np.nan values
# This 2 lines will have to be removed in future versions of numpy
warnings.filterwarnings('ignore')

logging.basicConfig(
  format='%(asctime)s %(levelname)s - %(name)s:%(lineno)3d - %(message)s', datefmt='%x %X',
)
logger = logging.getLogger('ProtonFlux')


NOAA_URL = 'https://services.swpc.noaa.gov/json/goes/primary/integral-protons-3-day.json'
WARNING_THRESHOLD = 10**2

class ProtonFlux:
  def __init__(self, cache_file, cache_time=900):
    self.cachefile = cache_file
    self.data = None
    logger.debug('Import Proton Flux')
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
    _re = re.compile(r'>=(\d+)\sMeV')

    def get_e(field):
      if match := _re.match(field):
        return match.group(1)
      return None

    with urllib.request.urlopen(NOAA_URL) as res:
      webdata = res.read()
      encoding = res.info().get_content_charset('utf-8')
      _data = json.loads(webdata.decode(encoding), object_hook=noaa_date_hook)

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

  def is_data(self):
    return bool(self.data)

  def graph(self, image_names):
    # pylint: disable=too-many-locals
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
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %HH'))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=12))
    ax.xaxis.set_minor_locator(mdates.HourLocator())

    dates  = np.array(list(self.data.keys()))

    _max = 0
    for _energy in energy:
      data = np.array([flux[_energy] for flux in self.data.values()])
      data = remove_outliers(data)
      ax.plot(dates, data, linewidth=1.25, color=colors[_energy], zorder=2,
              label=f'>={_energy} MeV')
      _max = max(data.max(), _max)

    magnitude = 1 + int(math.log(_max, 10))
    ax.set_ylim((0.1, 10**magnitude))

    if magnitude > WARNING_THRESHOLD:
      ax.axhline(WARNING_THRESHOLD, linewidth=1.5, linestyle="--", zorder=0, color='tab:red',
                 label='Warning Threshold')

    legend = ax.legend(loc='upper left', fontsize="12", facecolor="linen",
                       borderpad=1.25, borderaxespad=1)
    for line in legend.get_lines():
      if line.get_label().startswith('>'):
        line.set_linewidth(5.0)
      else:
        line.set_linewidth(2)

    today = datetime.utcnow().strftime('%Y/%m/%d %H:%M UTC')
    plt.figtext(0.01, 0.02, f'SunFluxBot By W6BSD {today}', fontsize=12)
    for name in image_names:
      try:
        fig.savefig(name, transparent=False, dpi=100)
        logger.info('Saved "%s"', name)
      except ValueError as err:
        logger.error(err)

    plt.close()


def main():
  logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))
  config = Config().get("proton_flux", {})

  parser = argparse.ArgumentParser()
  parser.add_argument('names', help='Name of the graph', nargs="*",
                      default=['/tmp/proton_flux.png'])
  opts = parser.parse_args()

  cache_file = config.get('cache_file', '/tmp/proton_flux.pkl')
  cache_time = config.get('cache_time', 900)

  p_f = ProtonFlux(cache_file, cache_time)
  if not p_f.is_data():
    logger.error('No data collected')
    return os.EX_DATAERR

  p_f.graph(opts.names)
  return os.EX_OK

if __name__ == "__main__":
  sys.exit(main())
