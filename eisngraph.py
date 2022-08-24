#!/usr/bin/env python3.9
#
import csv
import logging
import os
import pickle
import sys
import time

from datetime import datetime, date
from urllib.request import urlopen

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from config import Config

plt.style.use(['classic', 'seaborn-talk'])

SIDC_URL = 'https://www.sidc.be/silso/DATA/EISN/EISN_current.csv'

class EISN:
  def __init__(self, cache_file, cache_time=43200):
    self.log = logging.getLogger('EISN')
    self.data = EISN.read_cache(cache_file)

    if EISN.is_expired(cache_file, cache_time):
      self.log.info('Downloading data from SIDC')
      self.data = EISN.read_url(SIDC_URL, self.data)
      EISN.write_cache(cache_file, self.data)

  @staticmethod
  def read_url(url, current_data):
    with urlopen(url) as resp:
      if resp.status != 200:
        return current_data
      charset = resp.info().get_content_charset('utf-8')
      csvfd = csv.reader(r.decode(charset) for r in resp)
      data = current_data
      for fields in csvfd:
        data.append(EISN.convert(fields))

    # de-dup
    _data = {v[0]: v for v in data}
    return sorted(_data.values())[-90:]

  @staticmethod
  def convert(fields):
    ftmp = []
    for field in fields:
      field = field.strip()
      if str.isdecimal(field):
        ftmp.append(int(field))
      elif '.' in field:
        ftmp.append(float(field))
      else:
        ftmp.append(0)
    return (date(*ftmp[:3]), *ftmp[3:])

  @staticmethod
  def read_cache(cache_file):
    try:
      with open(cache_file, 'rb') as cfd:
        return pickle.load(cfd)
    except (FileNotFoundError, EOFError):
      return []

  @staticmethod
  def write_cache(cache_file, data):
    with open(cache_file, 'wb') as cfd:
      pickle.dump(data, cfd)

  @staticmethod
  def is_expired(cache_file, cache_time):
    now = time.time()
    try:
      filest = os.stat(cache_file)
      if now - filest.st_mtime > cache_time:
        return True
    except FileNotFoundError:
      return True
    return False

  def graph(self, filename):
    if not self.data:
      self.log.warning('No data to graph')
      return None

    x = np.array([d[0] for d in self.data])
    y = np.array([int(x[2]) for x in self.data])
    error = np.array([float(x[3]) for x in self.data])
    vdata = np.array([int(x[4]) for x in self.data])
    cdata = np.array([int(x[5]) for x in self.data])

    today = datetime.utcnow().strftime('%Y/%m/%d %H:%M')
    fig = plt.figure(figsize=(12, 5))
    fig.suptitle('Estimated International Sunspot Number (EISN)', fontsize=14, fontweight='bold')
    fig.text(0.01, 0.02, f'SunFluxBot By W6BSD {today}')
    axgc = plt.gca()
    axgc.tick_params(labelsize=10)
    axgc.plot(x, y, color="blue")
    axgc.plot(x, vdata, '^', linewidth=0, color='orange')
    axgc.plot(x, cdata, 'v', linewidth=0, color='green')
    axgc.errorbar(x, y, yerr=error, fmt='*', color='green',
                  ecolor='darkolivegreen', elinewidth=.8, capsize=5,
                  capthick=.8)
    axgc.fill_between(x, y-error, y+error, facecolor='plum', alpha=1.0,
                      linewidth=.75, edgecolor='b')

    axgc.legend(['EISN', 'Valid Data', 'Entries'], loc='upper left',
                facecolor="linen")

    loc = mdates.DayLocator(interval=5)
    axgc.xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d'))
    axgc.xaxis.set_major_locator(loc)
    axgc.xaxis.set_minor_locator(mdates.DayLocator())
    axgc.set_ylim(0, y.max()*1.2)

    axgc.grid(color="gray", linestyle="dotted", linewidth=.5)
    axgc.margins(.01)
    fig.autofmt_xdate(rotation=10, ha="center")
    plt.savefig(filename, transparent=False, dpi=100)
    plt.close()
    self.log.info('Graph "%s" saved', filename)
    return filename


def main():
  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s', datefmt='%H:%M:%S',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )
  config = Config()
  try:
    name = sys.argv[1]
  except IndexError:
    name = '/tmp/eisn.png'

  cache_file = config.get('eisngraph.cache_file', '/tmp/eisn.pkl')
  cache_time = config.get('eisngraph.cache_time', 43200)
  eisn = EISN(cache_file, cache_time)
  if not eisn.graph(name):
    return os.EX_DATAERR

  return os.EX_OK

if __name__ == "__main__":
  sys.exit(main())
