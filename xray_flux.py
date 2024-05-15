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
import pathlib
import pickle
import sys
import time
import urllib.request
import warnings
from datetime import datetime, timezone
from urllib.parse import urlparse

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import ticker

from config import Config
from tools import noaa_date, noaa_date_hook

logging.basicConfig(
  format='%(asctime)s %(levelname)s - %(name)s:%(lineno)3d - %(message)s', datefmt='%x %X',
)
logger = logging.getLogger('XRayFlux')

# Older versions of numpy are too verbose when arrays contain np.nan values
# This 2 lines will have to be removed in future versions of numpy
warnings.filterwarnings('ignore')

NOAA_XRAY3 = 'https://services.swpc.noaa.gov/json/goes/primary/xrays-3-day.json'
NOAA_XRAY7 = 'https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json'
NOAA_FLARE = 'https://services.swpc.noaa.gov/json/goes/primary/xray-flares-7-day.json'


def remove_outlier(points, low=25, high=95):
  percent_lo = np.percentile(points, low, interpolation='midpoint')
  percent_hi = np.percentile(points, high, interpolation='midpoint')
  iqr = percent_hi - percent_lo
  lower_bound = points <= (percent_lo - 5 * iqr)
  upper_bound = points >= (percent_hi + 5 * iqr)
  points[lower_bound | upper_bound] = np.nan
  return points


class XRayFlux:
  def __init__(self, source, cache_path, cache_time=900):
    self.source = source
    parsed_url = urlparse(source)
    cache_file = pathlib.Path(parsed_url.path).stem
    self.cachefile = pathlib.Path(cache_path).joinpath(cache_file + '.pkl')

    self.data = None
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

  def graph(self, image_names):
    # pylint: disable=too-many-locals
    dates = np.array(list(self.xray_data.keys()))
    data = np.array([d['flux'] for d in self.xray_data.values()])
    data = remove_outlier(data)
    data[data < 10**-7] = np.nan

    fig = plt.figure(figsize=(12, 5))
    fig.subplots_adjust(bottom=0.15)

    fig.suptitle('XRay Flux', fontsize=14, fontweight='bold')
    ax = plt.gca()
    ax.set_yscale("log")
    ax.tick_params(axis='x', which='both', labelsize=12, rotation=10)

    formatter = ticker.ScalarFormatter(useMathText=True)
    formatter.set_scientific(True)
    formatter.set_powerlimits((-1, 1))
    ax.grid(color='brown', linestyle='dotted', linewidth=.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d/%Y'))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_minor_locator(mdates.HourLocator())

    max_mag = int(math.log(data[data > 0.0].max(), 10)) + 1
    min_mag = int(math.log(data[data > 0.0].min(), 10)) - 1
    ax.set_ylim((10**min_mag, 10**max_mag))

    data[data == 0.0] = np.nan
    ax.plot(dates, data, linewidth=1.5, color="tab:blue", zorder=2, label='X-Ray Flux')

    class_colors = {'X': 'tab:red', 'M': 'tab:orange', 'C': 'tab:blue',
                    'B': 'tab:olive', 'A': 'tab:cyan'}
    for flare in self.flare_data:
      try:
        start = noaa_date(flare['begin_time'])
        end = noaa_date(flare['end_time'])
        if end < dates.min():
          continue
        fclass = (flare.get('max_class') or flare.get('end_class'))[0]
        ax.axvspan(mdates.date2num(start), mdates.date2num(end), color=class_colors[fclass],
                   label=f'{fclass} Class Flare', alpha=0.25)
      except TypeError as err:
        logger.warning("Data error: %s Ignoring", err)

    handles, labels = ax.get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    ax.legend(unique.values(), unique.keys(), loc='upper left', fontsize=12,
              facecolor="linen", borderpad=1, borderaxespad=1)

    today = datetime.now(timezone.utc).strftime('%Y/%m/%d %H:%M %Z')
    plt.figtext(0.01, 0.02, f'SunFlux By W6BSD {today}', fontsize=10)
    for name in image_names:
      try:
        fig.savefig(name, transparent=False, dpi=100)
        logger.info('Saved "%s"', name)
      except ValueError as err:
        logger.error(err)
    plt.close()


def main():
  logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))
  config = Config().get('xray_flux', {})
  cache_path = config.get('cache_path', '/tmp')
  graph_name = config.get('graph_name', '/tmp/xray_flux.png')
  cache_time = config.get('cache_time', 900)

  days = {
    "3": NOAA_XRAY3,
    "7": NOAA_XRAY7,
  }

  parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('-d', '--days', choices=days.keys(), default='3',
                      help="Number of days to graph (default: %(default)s)")
  parser.add_argument('graph_names', nargs="*", default=[graph_name],
                      help=("Name of the graph to generate (default: %(default)s)\n"
                            "Formats can be 'png', 'jpeg', 'webp', 'svg', or 'sgvz'"))
  opts = parser.parse_args()

  xray = XRayFlux(days[opts.days], cache_path, cache_time)
  xray.graph(opts.graph_names)


if __name__ == "__main__":
  sys.exit(main())
