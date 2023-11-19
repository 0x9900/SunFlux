#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c) 2022-2023 Fred W6BSD
# All rights reserved.
#
#

import argparse
import logging
import os
import sys
import time

from collections import namedtuple
from datetime import datetime
from urllib.request import urlretrieve

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from config import Config

plt.style.use(['classic', 'fast'])

logging.basicConfig(
  format='%(asctime)s %(name)s:%(lineno)3d - %(levelname)s - %(message)s', datefmt='%x %X',
)
logger = logging.getLogger('outloot')

NOAA_URL = 'https://services.swpc.noaa.gov/text/27-day-outlook.txt'

ALPHA=1

class Record(namedtuple("OLRecord", ["Date", "Flux", "AIndex", "KpIndex"])):
  def __new__(cls, items):
    _items = [datetime.strptime(' '.join(items[:3]), "%Y %b %d")]
    _items.extend([int(x.strip()) for x in items[3:]])
    return tuple.__new__(cls, _items)

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

  def graph(self, filenames):
    data = np.array(self.data)
    dates = data[:,0]
    flux = data[:,1]
    aindex = data[:,2]
    kindex = data[:,3]
    now = datetime.utcnow().strftime('%Y/%m/%d %H:%M UTC')

    fig = plt.figure(figsize=(12, 5))
    ax1 = plt.subplot(222)
    ax2 = plt.subplot(221)
    ax3 = plt.subplot(212)

    fig.tight_layout()
    fig.suptitle('27 day Solar Predictions', fontsize=14, fontweight='bold')

    # first axis
    self.draw_aindex(ax1, dates, aindex)
    self.draw_kindex(ax2, dates, kindex)
    self.draw_flux(ax3, dates, flux)

    for axe in [ax1, ax2, ax3]:
      axe.tick_params(axis='both', which='both', labelsize=10, rotation=10)
      axe.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
      axe.xaxis.set_minor_locator(mdates.DayLocator())

    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%a %b %d'))

    for day in [t.date() for t in dates[:-1]]:
      if day.isoweekday() not in (6, 7):
        continue
      for plot in [ax1, ax2, ax3]:
        plot.axvspan(mdates.date2num(day), mdates.date2num(day) + 1, color="skyblue", alpha=0.3)

    plt.figtext(0.80, 0.03, "Good", size=12,
                bbox=dict(boxstyle="round", color='springgreen', alpha=ALPHA))
    plt.figtext(0.87, 0.03, " OK ", size=12,
                bbox=dict(boxstyle="round", color='orange', alpha=ALPHA))
    plt.figtext(0.93, 0.03, "Bad", size=12,
                bbox=dict(boxstyle="round", color='tomato', alpha=ALPHA))

    plt.subplots_adjust(top=0.91, bottom=0.15)

    plt.figtext(0.01, 0.02, f'SunFluxBot By W6BSD {now}')
    for filename in filenames:
      plt.savefig(filename, transparent=False, dpi=100)
      logger.info('Graph "%s" saved', filename)
    plt.close()

  @staticmethod
  def draw_aindex(axe, dates, aindex):
    bars = axe.bar(dates, aindex, color='springgreen', label='AIndex', zorder=2)
    axe.set_ylim([0, aindex.max() * 1.15])
    axe.legend(loc='upper right', fontsize="10")
    axe.grid(color="gray", linewidth=.5)

    for hbar in bars:
      hbar.set_alpha(ALPHA)
      hbar.set_color('springgreen')
      value = hbar.get_height()
      if 5 < value <= 9:
        hbar.set_color('orange')
      elif value > 9:
        hbar.set_color('tomato')

  @staticmethod
  def draw_kindex(axe, dates, kindex):
    bars = axe.bar(dates, kindex, color="springgreen", label='Max KP-index', zorder=2)
    axe.set_ylim([0, kindex.max() * 1.25])
    axe.legend(loc='upper right', fontsize="10")
    axe.grid(color="black", linewidth=.5)

    for hbar in bars:
      hbar.set_alpha(ALPHA)
      hbar.set_color('springgreen')
      value = hbar.get_height()
      if 3 <= value < 5:
        hbar.set_color('orange')
      elif value >= 5:
        hbar.set_color('tomato')

  @staticmethod
  def draw_flux(axe, dates, flux):
    axe.plot(dates, flux, "navy", marker='.', linewidth=1.5, label='Flux')
    axe.set_ylim([min(flux)/1.2, max(flux) * 1.05])
    axe.legend(loc='upper right', fontsize="10")
    axe.axhspan(90, axe.get_yticks().max(), facecolor='springgreen', alpha=ALPHA/2, label='Good')
    axe.axhspan(70, 90, facecolor='orange', alpha=ALPHA/2, label='Ok')
    axe.axhspan(40, 70, facecolor='tomato', alpha=ALPHA/2, label='Bad')
    axe.grid(color="black", linewidth=.5)


def main():
  logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))
  config = Config().get('outlookgraph', {})

  parser = argparse.ArgumentParser()
  parser.add_argument('names', help='Name of the graph', nargs="*", default=['/tmp/outlook.png'])
  opts = parser.parse_args()

  cache_file = config.get('outlookgraph.cache_file', '/tmp/outlook.dat')
  cache_time = config.get('outlookgraph.cache_time', 43200)
  outlook = OutLook(cache_file, cache_time)
  if not outlook.is_data():
    logger.warning('No data to graph')
    return os.EX_DATAERR
  outlook.graph(opts.names)
  return os.EX_OK

if __name__ == "__main__":
  sys.exit(main())
