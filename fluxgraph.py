#!/usr/bin/env python3.9
#
import json
import logging
import os
import pickle
import sys
import time
import urllib.request

from datetime import datetime

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from config import Config

STYLE = 'dark_background'

plt.style.use(['classic', STYLE])

parameters = {
  'axes.labelsize': 12,
  'axes.titlesize': 20,
  'figure.figsize': [12, 8],
  'axes.labelcolor': 'gray',
  'axes.titlecolor': 'gray',
  'font.size': 12.0,
}
plt.rcParams.update(parameters)

class Flux:
  def __init__(self, cache_file):
    self.log = logging.getLogger('Flux')
    self.cachefile = cache_file
    self.data = None

    now = time.time()
    try:
      filest = os.stat(self.cachefile)
      if now - filest.st_atime > 43200:
        raise FileNotFoundError
    except FileNotFoundError:
      self.download_flux()
      if self.data:
        self.writecache()
    finally:
      self.readcache()

  def graph(self, filename):
    if not self.data:
      self.log.warning('No data to graph')
      return

    x = np.array([datetime.strptime(d[0], '%Y-%m-%d %H:%M:%S.%f') for d in self.data])
    y = np.array([int(x[1]) for x in self.data])

    plt.plot(x, y)
    plt.title('Daily 10cm Flux Index', fontsize=14)

    loc = mdates.DayLocator(interval=3)
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d'))
    plt.gca().xaxis.set_major_locator(loc)
    plt.gcf().autofmt_xdate()
    plt.grid()
    plt.savefig(filename, transparent=False, dpi=100)
    self.log.info('Graph "%s" saved', filename)
    return filename

  def download_flux(self):
    self.log.info('Downloading data from NOAA')
    res = urllib.request.urlopen('https://services.swpc.noaa.gov/products/10cm-flux-30-day.json')
    webdata = res.read()
    encoding = res.info().get_content_charset('utf-8')
    data = json.loads(webdata.decode(encoding))
    self.data = data[1:]

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

def main():
  logging.basicConfig(level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO')))
  config = Config()
  try:
    name = sys.argv[1]
  except IndexError:
    name = '/tmp/flux.png'

  cache_file = config.get('fluxgraph.cache_file', '/tmp/flux.pkl')
  flux = Flux(cache_file)
  flux.graph(name)

if __name__ == "__main__":
  main()
