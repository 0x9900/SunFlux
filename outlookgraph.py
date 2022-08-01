#!/usr/bin/env python3.9
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
    now = datetime.utcnow().strftime('%Y/%m/%d %H:%M')

    fig, ax1 = plt.subplots(figsize=(12, 5))
    fig.suptitle('27 day Solar Predictions', fontsize=16, fontweight='bold')
    plt.tick_params(labelsize=10)
    fig.autofmt_xdate(rotation=10, ha="center")

    # first axis
    ax1.plot(dates, aindex, ":b", linewidth=1.5, label='A-index')
    ax1.plot(dates, kindex, "--m", linewidth=1.5, label='KP-index')
    ax1.set_ylim([0, aindex.max() * 1.15])
    ax1.set_ylabel('Index')
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y %b %d'))
    ax1.grid(color="gray", linestyle="dotted", linewidth=.5)
    ax1.legend(loc='upper left')

    # second axis
    ax2 = ax1.twinx()
    ax2.plot(dates, flux, "darkgreen", linewidth=1.5, label='Flux')
    ax2.set_ylim([min(flux) * 0.95, max(flux) * 1.05])
    ax2.set_ylabel('Flux')
    ax2.grid(color="green", linestyle="dotted", linewidth=.5)
    ax2.legend(loc='upper right')

    plt.subplots_adjust(bottom=0.20)

    plt.figtext(0.01, 0.02, f'SunFluxBot By W6BSD {now}', rotation=90)
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
