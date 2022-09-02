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

NOAA_URL = 'https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json'

plt.style.use(['classic', 'seaborn-talk'])

def bucket(dtm):
  return int(6 * int(dtm.hour / 6))

class KPIndex:
  def __init__(self, cache_file, cache_time=21600):
    self.log = logging.getLogger('KPIndex')
    self.cachefile = cache_file
    self.data = None

    now = time.time()
    try:
      filest = os.stat(self.cachefile)
      if now - filest.st_mtime > cache_time: # 6 hours
        raise FileNotFoundError
    except FileNotFoundError:
      self.download()
      if self.data:
        self.writecache()
    finally:
      self.readcache()

  def graph(self, filename):
    if not self.data:
      self.log.warning('No data to graph')
      return None

    xdates = np.array([d[0] for d in self.data])
    yvalues = np.array([np.average(d[1]) for d in self.data])

    colors = ['lightgreen'] * len(yvalues)
    for pos, val in enumerate(yvalues):
      if int(val) == 4:
        colors[pos] = 'darkorange'
      elif val > 4:
        colors[pos] = 'red'

    date = datetime.utcnow().strftime('%Y:%m:%d %H:%M')
    plt.rc('xtick', labelsize=10)
    plt.rc('ytick', labelsize=10)
    fig = plt.figure(figsize=(12, 5))
    fig.suptitle('Planetary K-Index', fontsize=14, fontweight='bold')
    axgc = plt.gca()
    axgc.bar(xdates, yvalues, width=.2, linewidth=0.75, zorder=2, color=colors)
    axgc.axhline(y=4, linewidth=1, zorder=1.5, color='red', linestyle="dashed")

    loc = mdates.DayLocator(interval=1)
    axgc.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m-%d'))
    axgc.xaxis.set_major_locator(loc)
    axgc.xaxis.set_minor_locator(mdates.HourLocator(interval=6))
    axgc.set_ylim(0, 9)

    axgc.grid(color="gray", linestyle="dotted", linewidth=.5)
    fig.autofmt_xdate(rotation=10, ha="center")

    plt.figtext(0.02, 0.02, f'SunFluxBot By W6BSD {date}')
    plt.savefig(filename, transparent=False, dpi=100)
    plt.close()
    self.log.info('Graph "%s" saved', filename)
    return filename

  def download(self):
    self.log.info('Downloading data from NOAA')
    res = urllib.request.urlopen(NOAA_URL)
    webdata = res.read()
    encoding = res.info().get_content_charset('utf-8')
    _data = json.loads(webdata.decode(encoding))
    data = []
    for elem in _data[1:]:
      date = datetime.strptime(elem[0], '%Y-%m-%d %H:%M:%S.%f')
      date = date.replace(hour=bucket(date), minute=0, second=0, microsecond=0)
      data.append((date, int(elem[1])))
    self.data = sorted(data)

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
  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s', datefmt='%H:%M:%S',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )
  config = Config()
  try:
    name = sys.argv[1]
  except IndexError:
    name = '/tmp/kpindex.png'

  cache_file = config.get('kpindexgraph.cache_file', '/tmp/kpindex.pkl')
  cache_time = config.get('kpindexgraph.cache_time', 21600)
  kpindex = KPIndex(cache_file, cache_time)
  if not kpindex.graph(name):
    return os.EX_DATAERR

  return os.EX_OK

if __name__ == "__main__":
  sys.exit(main())
