#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c)2023 Fred W6BSD
# All rights reserved.
#
#

import argparse
import json
import logging
import math
import os
import pathlib
import pickle
import sys
import time
import urllib.request
import warnings
from collections import OrderedDict
from urllib.parse import urlparse

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import ticker

import tools
from config import Config
from tools import noaa_date, noaa_date_hook

logging.basicConfig(
  format='%(asctime)s %(levelname)s - %(name)s:%(lineno)3d - %(message)s', datefmt='%x %X',
  level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
)
logger = logging.getLogger('XRayFlux')

# Older versions of numpy are too verbose when arrays contain np.nan values
# This 2 lines will have to be removed in future versions of numpy
warnings.filterwarnings('ignore')

NOAA_XRAY1 = 'https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json'
NOAA_XRAY3 = 'https://services.swpc.noaa.gov/json/goes/primary/xrays-3-day.json'
NOAA_XRAY7 = 'https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json'
NOAA_FLARE = 'https://services.swpc.noaa.gov/json/goes/primary/xray-flares-7-day.json'


class XRayFlux:
  def __init__(self, source, cache_path, cache_time=900):
    self.source = source
    parsed_url = urlparse(source)
    cache_file = pathlib.Path(parsed_url.path).stem
    self.cachefile = pathlib.Path(cache_path).joinpath(cache_file + '.pkl')

    logger.debug('Import XRay Flux')
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
    logger.info('Downloading XRayFlux data from NOAA into %s', self.cachefile)

    with urllib.request.urlopen(self.source) as res:
      webdata = res.read()
      encoding = res.info().get_content_charset('utf-8')
      _data = json.loads(webdata.decode(encoding), object_hook=noaa_date_hook)
    self.xray_data = {e['time_tag']: e for e in _data}

    with urllib.request.urlopen(NOAA_FLARE) as res:
      webdata = res.read()
      encoding = res.info().get_content_charset('utf-8')
      self.flare_data = json.loads(webdata.decode(encoding))

  def readcache(self):
    """Read data from the cache"""
    logger.debug('Read from cache "%s"', self.cachefile)
    try:
      with open(self.cachefile, 'rb') as fd_cache:
        self.xray_data = pickle.load(fd_cache)
        self.flare_data = pickle.load(fd_cache)
    except (FileNotFoundError, EOFError):
      self.xray_data = None
      self.flare_data = None

  def writecache(self):
    """Write data into the cachefile"""
    logger.debug('Write cache "%s"', self.cachefile)
    with open(self.cachefile, 'wb') as fd_cache:
      pickle.dump(self.xray_data, fd_cache)
      pickle.dump(self.flare_data, fd_cache)

  def graph(self, filename, style):
    # pylint: disable=too-many-locals
    dates = np.array(list(self.xray_data.keys()))
    data = np.array([d['flux'] for d in self.xray_data.values()])
    data[data < 10**-7] = np.nan

    fig = plt.figure(figsize=(12, 5))
    fig.subplots_adjust(bottom=0.15)

    fig.suptitle('XRay Flux')
    ax = plt.gca()
    ax.set_yscale("log")
    ax.tick_params(axis='x', which='both', rotation=10)

    formatter = ticker.ScalarFormatter(useMathText=True)
    formatter.set_scientific(True)
    formatter.set_powerlimits((-1, 1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d/%Y'))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_minor_locator(mdates.HourLocator())
    ax.set_ylabel(r'$Watts \cdot M^{-2}$')

    max_mag = int(math.log(data[data > 0.0].max(), 10)) + 1
    min_mag = int(math.log(data[data > 0.0].min(), 10)) - 1
    ax.set_ylim((10**min_mag, 10**max_mag))

    data[data == 0.0] = np.nan
    ax.plot(dates, data, linewidth=1, zorder=2, label='X-Ray Flux')

    class_colors = {
      'X': style.colors[3],
      'M': style.colors[6],
      'C': 'darkgray',
      'B': 'darkgray',
      'A': 'darkgray',
    }
    for flare in self.flare_data:
      try:
        start = noaa_date(flare['begin_time'])
        end = noaa_date(flare['end_time'])
        if end < dates.min():
          continue
        fclass = (flare.get('max_class') or flare.get('end_class'))[0]
        if fclass in ('A', 'B', 'C'):
          continue
        ax.axvspan(mdates.date2num(start), mdates.date2num(end), color=class_colors[fclass],
                   label=f'{fclass} Class Flare', alpha=0.33)
      except TypeError as err:
        logger.debug("Missing data: %s Ignoring", err)

    handles, labels = ax.get_legend_handles_labels()

    unique = OrderedDict(sorted(zip(labels, handles), key=lambda x: x[0]))
    ax.legend(unique.values(), unique.keys(), loc='upper left')

    tools.save_plot(plt, filename)
    plt.close()


def main():
  config = Config().get('xray_flux', {})
  cache_path = config.get('cache_path', '/tmp')
  cache_time = config.get('cache_time', 900)
  target_dir = config.get('target_dir', '/var/www/html')

  days = {
    "1": NOAA_XRAY1,
    "3": NOAA_XRAY3,
    "7": NOAA_XRAY7,
  }

  parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('-d', '--days', choices=days.keys(), default='3',
                      help="Number of days to graph (default: %(default)s)")
  parser.add_argument('-t', '--target', type=pathlib.Path, default=target_dir,
                      help='Image path')
  opts = parser.parse_args()

  xray = XRayFlux(days[opts.days], cache_path, cache_time)

  for style in tools.STYLES:
    with plt.style.context(style.style):
      filename = opts.target.joinpath(f'xray_flux{opts.days}-{style.name}')
      xray.graph(filename, style)
      if opts.days == '3':
        tools.mk_link(filename, opts.target.joinpath(f'xray_flux-{style.name}'))
        if style.name == 'light':
          tools.mk_link(filename, opts.target.joinpath('xray_flux'))

  return os.EX_OK


if __name__ == "__main__":
  sys.exit(main())
