#!/usr/bin/env python3.9
#
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

from matplotlib.dates import DateFormatter, DayLocator
from matplotlib.ticker import AutoMinorLocator

from config import Config

plt.style.use(['classic', 'seaborn-talk'])

NOAA_URL = 'https://services.swpc.noaa.gov/text/daily-solar-indices.txt'

class SSN:
  def __init__(self, cache_file, cache_time=43200):
    self.log = logging.getLogger('SSN')
    self.data = SSN.read_cache(cache_file)

    if SSN.is_expired(cache_file, cache_time):
      self.log.info('Downloading data from NOAA')
      self.data = SSN.read_url(NOAA_URL, self.data)
      SSN.write_cache(cache_file, self.data)

  @staticmethod
  def read_url(url, current_data):
    with urlopen(url) as resp:
      if resp.status != 200:
        return current_data
      charset = resp.info().get_content_charset('utf-8')
      data = current_data
      for line in resp:
        line = line.decode(charset).strip()
        if not line or line[0] in ('#', ':'):
          continue
        data.append(SSN.convert(line))

    # de-dup
    _data = {v[0]: v for v in data}
    return sorted(_data.values())[-90:]

  @staticmethod
  def convert(line):
    #                         Sunspot       Stanford GOES15
    #           Radio  SESC     Area          Solar  X-Ray  ------ Flares ------
    #           Flux  Sunspot  10E-6   New     Mean  Bkgd    X-Ray      Optical
    #  Date     10.7cm Number  Hemis. Regions Field  Flux   C  M  X  S  1  2  3
    fields = line.split()[:6]
    fields = [int(f) for f in fields]
    return (date(*fields[:3]), *fields[3:])

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
    ssn = np.array([x[2] for x in self.data])
    flux = np.array([x[1] for x in self.data])

    today = datetime.utcnow().strftime('%Y/%m/%d %H:%M')
    fig = plt.figure(figsize=(12, 5))
    fig.suptitle('Sunspot Number (SSN)', fontsize=14)
    fig.text(0.01, 0.02, f'SunFluxBot By W6BSD {today}')
    axgc = plt.gca()
    axgc.tick_params(labelsize=10)
    axgc.plot(x, ssn, marker='o', markersize=7, color="darkolivegreen", linewidth=2)
    axgc.plot(x, flux, linestyle='--', color="cornflowerblue", linewidth=1)
    loc = mdates.DayLocator(interval=5)
    axgc.xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d'))
    axgc.xaxis.set_major_locator(loc)
    axgc.xaxis.set_minor_locator(DayLocator())

    axgc.set_ylim(np.min([ssn, flux])*0.2, np.max([ssn, flux])*1.2)


    axgc.legend(['Sun spot', '10.7cm Flux'], facecolor="linen")
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
    name = '/tmp/ssn.png'

  cache_file = config.get('ssngraph.cache_file', '/tmp/ssn.pkl')
  cache_time = config.get('ssngraph.cache_time', 43200)
  ssn = SSN(cache_file, cache_time)
  if not ssn.graph(name):
    return os.EX_DATAERR

  return os.EX_OK

if __name__ == "__main__":
  sys.exit(main())
