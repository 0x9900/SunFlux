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

NOAA_URL = 'https://services.swpc.noaa.gov/json/boulder_k_index_1m.json'

parameters = {
  'axes.labelsize': 12,
  'axes.titlesize': 20,
  'figure.figsize': [12, 8],
  'axes.labelcolor': 'gray',
  'axes.titlecolor': 'gray',
  'font.size': 12.0,
}
plt.rcParams.update(parameters)
plt.style.use(['classic', 'seaborn-talk'])

class KPIndex:
  def __init__(self, cache_file, cache_time=21600):
    self.log = logging.getLogger('KPIndex')
    self.cachefile = cache_file
    self.data = None

    now = time.time()
    try:
      filest = os.stat(self.cachefile)
      if now - filest.st_atime > cache_time: # 6 hours
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

    x = np.array([datetime.strptime(d['time_tag'], '%Y-%m-%dT%H:%M:%S')
                  for d in self.data])
    y = np.array([round(x['k_index'], 2) for x in self.data])

    date = datetime.utcnow().strftime('%Y:%m:%d %H:%M')
    fig = plt.figure()
    fig.suptitle('Planetary KPIndex (Boulder)', fontsize=14)
    fig.text(0.01, 0.02, f'SunFluxBot By W6BSD {date}')
    axgc = plt.gca()
    axgc.plot(x, y)

    loc = mdates.HourLocator(interval=2)
    axgc.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:S'))
    axgc.xaxis.set_major_locator(loc)
    axgc.grid()
    fig.autofmt_xdate()
    plt.savefig(filename, transparent=False, dpi=100)
    plt.close()
    self.log.info('Graph "%s" saved', filename)
    return filename

  def download(self):
    self.log.info('Downloading data from NOAA')
    res = urllib.request.urlopen(NOAA_URL)
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
