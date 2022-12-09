#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c) 2022 Fred W6BSD
# All rights reserved.
#
#

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

plt.style.use(['classic', 'seaborn-talk'])

NOAA_URL = 'https://services.swpc.noaa.gov/text/27-day-outlook.txt'

ALPHA=0.3

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

  def graph(self, filename):
    if not self.data:
      self.log.warning('No data to graph')
      return None

    dates = np.array([d[0] for d in self.data])
    flux = np.array([int(x[1]) for x in self.data])
    aindex = np.array([int(x[2]) for x in self.data])
    kindex = np.array([int(x[3]) for x in self.data])
    now = datetime.utcnow().strftime('%Y/%m/%d %H:%M UTC')

    plt.rc('ytick', labelsize=12)
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 5))
    fig.tight_layout()
    fig.suptitle('27 day Solar Predictions', fontsize=14, fontweight='bold')
    plt.tick_params(labelsize=10)
    fig.autofmt_xdate(rotation=5, ha="center")

    # first axis
    ax1.plot(dates, aindex, linewidth=1.5, color="darkblue", label='A-index')
    ax1.set_ylim([1, aindex.max() * 1.15])
    loc = mdates.DayLocator(interval=int(1+len(aindex)/11))
    ax1.legend(loc='upper right', fontsize="10")
    ax1.axhspan(0, 5, facecolor='lightgreen', alpha=ALPHA, label='Good')
    ax1.axhspan(5, 9, facecolor='orange', alpha=ALPHA, label='Ok')
    ax1.axhspan(9, ax1.get_yticks().max(), facecolor='red', alpha=ALPHA, label='Bad')
    ax1.grid(color="black", linewidth=.5)

    ax2.plot(dates, kindex, linewidth=1.5, color="navy", label='KP-index')
    ax2.set_ylim([kindex.min() / 1.3, kindex.max() * 1.25])
    ax2.legend(loc='upper right', fontsize="10")
    ax2.axhspan(0, 3, facecolor='lightgreen', alpha=ALPHA, label='Good')
    ax2.axhspan(3, 5, facecolor='orange', alpha=ALPHA, label='Ok')
    ax2.axhspan(5, ax2.get_yticks().max(), facecolor='red', alpha=ALPHA, label='Bad')
    ax2.grid(color="black", linewidth=.5)

    ax3.plot(dates, flux, "brown", linewidth=1.5, label='Flux')
    ax3.set_ylim([min(flux)/1.1, max(flux) * 1.05])
    ax3.legend(loc='upper right', fontsize="10")
    ax3.axhspan(90, ax3.get_yticks().max(), facecolor='lightgreen', alpha=ALPHA, label='Good')
    ax3.axhspan(70, 90, facecolor='orange', alpha=ALPHA, label='Ok')
    ax3.axhspan(40, 70, facecolor='red', alpha=ALPHA, label='Bad')
    ax3.grid(color="black", linewidth=.5)

    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d UTC'))
    ax3.xaxis.set_major_locator(loc)
    ax3.xaxis.set_minor_locator(mdates.DayLocator())

    for day in [t.date() for t in dates[:-1]]:
      if day.isoweekday() != 6:
        continue
      for plot in [ax1, ax2, ax3]:
        plot.axvspan(mdates.date2num(day), mdates.date2num(day) + 1, color="skyblue", alpha=0.5)

    plt.figtext(0.80, 0.03, "Good", size=12,
                bbox=dict(boxstyle="round", color='lightgreen', alpha=0.5))
    plt.figtext(0.87, 0.03, " OK ", size=12,
                bbox=dict(boxstyle="round", color='orange', alpha=ALPHA))
    plt.figtext(0.93, 0.03, "Bad", size=12,
                bbox=dict(boxstyle="round", color='red', alpha=ALPHA))


    plt.subplots_adjust(top=0.93, bottom=0.15)

    plt.figtext(0.01, 0.02, f'SunFluxBot By W6BSD {now}')
    plt.savefig(filename, transparent=False, dpi=100)
    plt.close()
    self.log.info('Graph "%s" saved', filename)
    return filename

def main():
  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s',
    datefmt='%H:%M:%S',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )
  config = Config()
  try:
    name = sys.argv[1]
  except IndexError:
    name = '/tmp/outlook.png'

  cache_file = config.get('outlookgraph.cache_file', '/tmp/outlook.dat')
  cache_time = config.get('outlookgraph.cache_time', 43200)
  outlook = OutLook(cache_file, cache_time)
  if not outlook.graph(name):
    return os.EX_DATAERR

  return os.EX_OK

if __name__ == "__main__":
  sys.exit(main())
