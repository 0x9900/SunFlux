#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c) 2022 Fred W6BSD
# All rights reserved.
#
#

import json
import logging
import os
import sys
import time

from datetime import (datetime, timedelta)
from urllib import request

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from matplotlib.ticker import MultipleLocator

from config import Config

plt.style.use(['classic', 'fast'])

URL_HISTORY  = 'https://services.swpc.noaa.gov/json/solar-cycle/sunspots.json'
URL_PREDICTIONS = 'https://services.swpc.noaa.gov/products/solar-cycle-25-ssn-predicted-range.json'

def moving_average(data, window=12):
  average = np.convolve(data, np.ones(window), 'valid') / window
  for _ in range(window - 1):
    average = np.insert(average, 0, np.nan)
  return average


def _history_cache(cache_file):
  with open(cache_file, 'r', encoding='ASCII') as cfd:
    data = json.load(cfd)
  for item in data:
    item['time-tag'] = datetime.strptime(item['time-tag'], '%Y-%m')
  return data


def _predictions_cache(cache_file):
  with open(cache_file, 'r', encoding='ASCII') as cfd:
    data = json.load(cfd)
  for item in data:
    item['time-tag'] = datetime.strptime(item['time-tag'], '%Y-%m')
    if item['smoothed_ssn_min'] < 0.0:
      item['smoothed_ssn_min'] = 0.0
    item['ssn'] = np.average([item['smoothed_ssn_min'], item['smoothed_ssn_max']])
  return data


def download_history(cache_file, cache_time=86400):
  now = time.time()
  try:
    filest = os.stat(cache_file)
    if now - filest.st_mtime > cache_time:
      raise FileNotFoundError
  except FileNotFoundError:
    logging.info('Downloading history data from NOAA')
    request.urlretrieve(URL_HISTORY, cache_file)
  data = _history_cache(cache_file)
  return data


def download_predictions(cache_file, cache_time=86400):
  now = time.time()
  try:
    filest = os.stat(cache_file)
    if now - filest.st_mtime > cache_time:
      raise FileNotFoundError
  except FileNotFoundError:
    logging.info('Downloading predictions data from NOAA')
    request.urlretrieve(URL_PREDICTIONS, cache_file)
  data = _predictions_cache(cache_file)
  return data


def graph(histo, predic, image='/tmp/ssnhist.png', year=1970):
  start_date = datetime(year, 1, 1)
  end_date = datetime.utcnow() + timedelta(days=365*12)

  xdates = np.array([d['time-tag'] for d in histo if d['time-tag'] > start_date])
  yvals = np.array([d['ssn'] for d in histo if d['time-tag'] > start_date])
  mavg = moving_average(yvals)

  pdates = np.array([d['time-tag'] for d in predic if d['time-tag'] < end_date])
  lvals = np.array([d['smoothed_ssn_min'] for d in predic if d['time-tag'] < end_date])
  hvals = np.array([d['smoothed_ssn_max'] for d in predic if d['time-tag'] < end_date])
  pavg = np.array([d['ssn'] for d in predic if d['time-tag'] < end_date])

  today = datetime.utcnow().strftime('%Y/%m/%d %H:%M UTC')
  fig = plt.figure(figsize=(12, 5))
  fig.suptitle(f'SSN History from {year}', fontsize=14, fontweight='bold')
  plt.figtext(0.01, 0.02, f'SunFluxBot By W6BSD {today}')

  axis = plt.gca()
  axis.plot(xdates, mavg, label='Average', zorder=5, color="navy", linewidth=1.5)
  axis.plot(xdates, yvals, label='Sun Spots', zorder=4, color='gray', linewidth=1.25)
  axis.plot(pdates, pavg, zorder=4, color='blue', linewidth=.75, alpha=.3)
  axis.fill_between(pdates, lvals, hvals, label='Predicted', zorder=0, facecolor='powderblue',
                    alpha=0.9, linewidth=.75, edgecolor='lightblue')

  axis.axhline(y=yvals.mean(), label='All time mean', zorder=1, color='blue', linewidth=.5,
               linestyle='dashed')

  axis.set_xlabel('Years')
  axis.set_ylabel('Sun Spot Number')
  axis.tick_params(labelsize=10)
  axis.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
  axis.xaxis.set_major_locator(mdates.YearLocator(5, month=1, day=1))
  axis.xaxis.set_minor_locator(mdates.YearLocator())
  axis.yaxis.set_major_locator(MultipleLocator(25))
  axis.yaxis.set_minor_locator(MultipleLocator(5))

  axis.legend(facecolor="linen", fontsize="12", loc='best')
  axis.grid(color="gray", linestyle="dotted", linewidth=.5)

  plt.subplots_adjust(bottom=0.15)

  plt.savefig(image, transparent=False, dpi=100)
  plt.close()
  logging.info('Graph "%s" saved', image)

def main():
  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s', datefmt='%H:%M:%S',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )
  config = Config()
  try:
    name = sys.argv[1]
  except IndexError:
    name = '/tmp/ssnhist.png'

  cache_histo = config.get('ssnhist.cache_history', '/tmp/ssnhist.json')
  cache_predict = config.get('ssnhist.cache_precictions', '/tmp/ssnpredict.json')
  cache_time = config.get('ssnhist.cache_time', 86400)

  histo = download_history(cache_histo, cache_time)
  predict = download_predictions(cache_predict, cache_time)

  graph(histo, predict, name, 1975)


if __name__ == "__main__":
  main()
