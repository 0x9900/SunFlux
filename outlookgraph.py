#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c)2022-2025 Fred W6BSD
# All rights reserved.
#
#

import argparse
import logging
import os
import pathlib
import sys
import time
from collections import namedtuple
from datetime import datetime
from urllib.request import urlretrieve

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

import tools
from config import Config

logging.basicConfig(
  format='%(asctime)s %(levelname)s - %(name)s:%(lineno)3d - %(message)s', datefmt='%x %X',
  level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
)
logger = logging.getLogger('outloot')

NOAA_URL = 'https://services.swpc.noaa.gov/text/27-day-outlook.txt'

ALPHA = 1


class Record(namedtuple("OLRecord", ["Date", "Flux", "AIndex", "KpIndex"])):
  __slots__ = ()  # reduces memory usage

  def __new__(cls, items):
    date = datetime.strptime(' '.join(items[:3]), "%Y %b %d")
    flux, aindex, kpindex = (int(x.strip()) for x in items[3:])
    return super().__new__(cls, date, flux, aindex, kpindex)


class OutLook:
  def __init__(self, cache_file, cache_time=43200):
    self.log = logging.getLogger('OutLook')
    self.data = []

    now = time.time()
    try:
      filest = os.stat(cache_file)
      if now - filest.st_mtime > cache_time:
        raise FileNotFoundError
    except FileNotFoundError:
      self.log.info('Downloading data from NOAA')
      urlretrieve(NOAA_URL, cache_file)
    self.read_cache(cache_file)

  def read_cache(self, cache_file):
    with open(cache_file, 'r', encoding='ASCII') as cfd:
      for line in cfd.readlines():
        line = line.rstrip()
        if not line or line[0] in (':', '#'):
          continue
        self.data.append(Record(line.split()))

  def is_data(self):
    return bool(self.data)

  def graph(self, filename):
    # pylint: disable=too-many-locals
    data = np.array(self.data)
    dates = data[:, 0]
    flux = data[:, 1]
    aindex = data[:, 2]
    kindex = data[:, 3]

    fig = plt.figure(figsize=(12, 5))
    ax1 = plt.subplot(222)
    ax2 = plt.subplot(221)
    ax3 = plt.subplot(212)

    fig.tight_layout()
    fig.suptitle('27 day Solar Predictions')

    # first axis
    self.draw_aindex(ax1, dates, aindex)
    self.draw_kindex(ax2, dates, kindex)
    self.draw_flux(ax3, dates, flux)

    for axe in [ax1, ax2, ax3]:
      axe.tick_params(axis='both', which='both', labelsize=8, rotation=10)
      axe.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
      axe.xaxis.set_minor_locator(mdates.DayLocator())
      axe.grid(False)

    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%a %b %d'))

    for day in [t.date() for t in dates[:-1]]:
      if day.isoweekday() not in (6, 7):
        continue
      for plot in [ax1, ax2, ax3]:
        plot.axvspan(mdates.date2num(day), mdates.date2num(day) + 1, alpha=0.1)

    plt.subplots_adjust(top=0.91, bottom=0.15)

    tools.save_plot(plt, filename)
    plt.close()

  @staticmethod
  def draw_aindex(axe, dates, aindex):
    bars = axe.bar(dates, aindex, color='springgreen', label='AIndex', zorder=2)
    axe.set_ylim([0, aindex.max() * 1.15])
    axe.legend(loc='upper right')

    for hbar in bars:
      hbar.set_color('springgreen')
      value = hbar.get_height()
      if 5 < value <= 9:
        hbar.set_color('orange')
      elif value > 9:
        hbar.set_color('tomato')

  @staticmethod
  def draw_kindex(axe, dates, kindex):
    bars = axe.bar(dates, kindex, color="springgreen", label='Max KP-index', zorder=5)
    axe.set_ylim([0, kindex.max() * 1.25])
    axe.legend(loc='upper right')

    for hbar in bars:
      hbar.set_color('springgreen')
      value = hbar.get_height()
      if 3 <= value < 5:
        hbar.set_color('orange')
      elif value >= 5:
        hbar.set_color('tomato')

  @staticmethod
  def draw_flux(axe, dates, flux):
    axe.plot(dates, flux, marker='.', linewidth=1.5, label='Flux')
    axe.set_ylim([min(flux) / 1.2, max(flux) * 1.05])
    axe.legend(loc='upper right')


def main():
  config = Config().get('outlookgraph', {})
  cache_file = config.get('outlookgraph.cache_file', '/tmp/outlook.dat')
  cache_time = config.get('outlookgraph.cache_time', 43200)
  target_dir = config.get('target_dir', '/var/www/html')

  parser = argparse.ArgumentParser()
  parser.add_argument('-t', '--target', type=pathlib.Path, default=target_dir,
                      help='Image path')
  opts = parser.parse_args()

  outlook = OutLook(cache_file, cache_time)
  if not outlook.is_data():
    logger.warning('No data to graph')
    return os.EX_DATAERR

  styles = tools.STYLES
  for style in styles:
    with plt.style.context(style.style):
      filename = opts.target / f'outlook-{style.name}'
      outlook.graph(filename)
      if style.name == 'light':
        tools.mk_link(filename, opts.target / 'outlook')

  return os.EX_OK


if __name__ == "__main__":
  sys.exit(main())
