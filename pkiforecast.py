#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c)2022-2023 Fred W6BSD
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
from datetime import datetime, timedelta, timezone

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MultipleLocator

import tools
from config import Config

NOAA_URL = 'https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json'

logging.basicConfig(
  format='%(asctime)s %(levelname)s - %(name)s:%(lineno)3d - %(message)s', datefmt='%x %X',
  level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
)
logger = logging.getLogger('pkiforecast')


class PKIForecast:
  def __init__(self, cache_file, cache_time=21600):
    self.cachefile = cache_file
    self.data = None

    now = time.time()
    try:
      filest = os.stat(self.cachefile)
      if now - filest.st_mtime > cache_time:  # 6 hours
        raise FileNotFoundError
    except FileNotFoundError:
      self.download()
      if self.data:
        self.writecache()
    finally:
      self.readcache()

  def is_data(self):
    return bool(self.data)

  def graph(self, filename, style):
    # pylint: disable=too-many-locals,too-many-statements
    start_date = datetime.now(timezone.utc) - timedelta(days=3, hours=4)
    end_date = datetime.now(timezone.utc) + timedelta(days=1, hours=3)
    xdates = np.array([d[0] for d in self.data if start_date < d[0] < end_date])
    yvalues = np.array([d[1] for d in self.data if start_date < d[0] < end_date])
    observ = [d[2] for d in self.data if start_date < d[0] < end_date]
    labels = [d[3] for d in self.data if start_date < d[0] < end_date]

    # colors #6efa7b #a7bbb36 #aa7f28 #8c4d30 #582a2d
    colors = [style.colors[1]] * len(observ)
    for pos, (obs, val) in enumerate(zip(observ, yvalues)):
      if obs == 'observed':
        if 4 < val <= 5:
          colors[pos] = style.colors[3]
        elif 5 < val <= 6:
          colors[pos] = style.colors[5]
        elif 6 < val <= 8:
          colors[pos] = style.colors[6]
        elif val > 8:
          colors[pos] = style.colors[8]
      elif obs == "estimated":
        colors[pos] = style.top
      elif obs == "predicted":
        colors[pos] = style.bottom

    fig = plt.figure(figsize=(12, 5))
    fig.suptitle('Planetary K-Index Predictions')
    axgc = plt.gca()
    bars = axgc.bar(xdates, yvalues, width=.1, linewidth=0.75, zorder=2, color=colors)
    axgc.axhline(y=4, linewidth=1.5, zorder=1, color='red', label='Storm Threshold')

    for rect, label in ((a, b) for a, b in zip(*(bars, labels)) if labels):
      if not label:
        continue
      axgc.text(rect.get_x() + rect.get_width() / 2., .3, label, alpha=1, fontsize=10,
                color="#0f0f0f", ha='center')

    loc = mdates.DayLocator(interval=1)
    axgc.xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d UTC'))
    axgc.xaxis.set_major_locator(loc)
    axgc.xaxis.set_minor_locator(mdates.HourLocator(interval=6))
    axgc.yaxis.set_major_locator(MultipleLocator(1))

    axgc.set_ylim(0, 9.5 if yvalues.max() > 5 else yvalues.max() * 1.8)
    axgc.set_ylabel('K-Index')

    axgc.axhspan(0, 0, facecolor=style.top, alpha=1, label='Estimated')
    axgc.axhspan(0, 0, facecolor=style.bottom, alpha=1, label='Predicted')
    axgc.legend()

    fig.autofmt_xdate(rotation=10, ha="center")

    tools.save_plot(plt, filename)
    plt.close()

  def download(self):
    logger.info('Downloading data from NOAA')
    data = []

    with urllib.request.urlopen(NOAA_URL) as res:
      webdata = res.read()
      encoding = res.info().get_content_charset('utf-8')
      _data = json.loads(webdata.decode(encoding))
      for elem in _data[1:]:
        date = datetime.strptime(elem[0], '%Y-%m-%d %H:%M:%S')
        date = date.replace(tzinfo=timezone.utc)
        data.append((date, float(elem[1]), *elem[2:]))

    self.data = sorted(data)

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


def main():
  config = Config().get('pkiforecast', {})
  cache_file = config.get('cache_file', '/tmp/pkiforecast.pkl')
  cache_time = config.get('cache_time', 21600)
  target_dir = config.get('target_dir', '/var/www/html')

  parser = argparse.ArgumentParser()
  parser.add_argument('-t', '--target', type=pathlib.Path, default=target_dir,
                      help='Image path')
  opts = parser.parse_args()

  pki = PKIForecast(cache_file, cache_time)
  if not pki.is_data():
    logger.warning('No data to graph')
    return os.EX_DATAERR

  styles = tools.STYLES
  for style in styles:
    with plt.style.context(style.style):
      filename = opts.target.joinpath(f'pki-forecast-{style.name}')
      pki.graph(filename, style)
      if style.name == 'light':
        tools.mk_link(filename, opts.target.joinpath('pki-forecast'))

  return os.EX_OK


if __name__ == "__main__":
  sys.exit(main())
