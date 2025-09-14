#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c)2022-2025 Fred W6BSD
# All rights reserved.
#
#

import argparse
import json
import logging
import os
import pathlib
import sys
import time
from datetime import datetime, timedelta
from urllib import request

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MultipleLocator

import tools
from config import Config

logging.basicConfig(
  format='%(asctime)s %(levelname)s - %(name)s:%(lineno)3d - %(message)s', datefmt='%x %X',
  level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
)
logger = logging.getLogger('ssnhist')

TREND_YEARS = 16
URL_HISTORY = 'https://services.swpc.noaa.gov/json/solar-cycle/sunspots.json'
URL_PREDICTIONS = 'https://services.swpc.noaa.gov/products/solar-cycle-25-ssn-predicted-range.json'


def moving_average(data, window=7):
  average = np.convolve(data, np.ones(window), 'valid') / window
  for _ in range(window - 1):
    average = np.insert(average, 0, np.nan)
  return average


def _history_cache(cache_file):
  with open(cache_file, 'r', encoding='ASCII') as cfd:
    data = json.load(cfd)
  data = [tuple(v.values()) for v in data]
  dtype = [('time_tag', 'datetime64[D]'), ('ssn', 'float64')]
  data = np.array(data, dtype=dtype)

  return data


def _predictions_cache(cache_file):
  with open(cache_file, 'r', encoding='ASCII') as cfd:
    data = json.load(cfd)

  data = [tuple(d.values()) for d in data]
  dtype = [
    ('time_tag', 'datetime64[M]'),
    ('smoothed_ssn_min', 'float64'),
    ('smoothed_ssn_max', 'float64')
  ]
  data = np.array(data, dtype=dtype)
  data['smoothed_ssn_min'][data['smoothed_ssn_min'] < 0.0] = 0.0
  return data


def download_history(cache_file, cache_time=86400):
  now = time.time()
  try:
    filest = os.stat(cache_file)
    if now - filest.st_mtime > cache_time:
      raise FileNotFoundError
  except FileNotFoundError:
    logger.info('Downloading history data from NOAA')
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
    logger.info('Downloading predictions data from NOAA')
    request.urlretrieve(URL_PREDICTIONS, cache_file)
  data = _predictions_cache(cache_file)
  return data


def graph(histo, predic, filename, style, year=1961):
  # pylint: disable=too-many-locals
  start_date = np.datetime64(f'{year}', 'D')
  end_date = np.datetime64(datetime.now() + timedelta(days=365 * 12), 'D')
  last_date = histo['time_tag'][-1].astype(object).year
  histo = histo[histo['time_tag'] > start_date]
  mavg = moving_average(histo['ssn'], 7)

  predic = predic[predic['time_tag'] < end_date]
  pavg = np.mean([predic['smoothed_ssn_min'], predic['smoothed_ssn_max']], axis=0)

  fig = plt.figure(figsize=(12, 5))
  fig.suptitle(f'SunSpot Numbers from {year} to {last_date}')

  axis = plt.gca()
  xdates = histo['time_tag']
  axis.plot(xdates, histo['ssn'], label='Sun Spots', zorder=4, linewidth=0.75)
  axis.plot(xdates, mavg, label='Average', zorder=5, linewidth=1.5)
  axis.axhline(y=histo['ssn'].mean(), label='All time mean', zorder=1, linewidth=.25,
               linestyle='dashed')

  # Calculate the trend for the last {TREND_YEARS}
  idx = histo['time_tag'] > np.datetime64(f'{last_date - TREND_YEARS}', 'D')
  trend_dates = histo['time_tag'][idx].astype('float64')
  poly = np.poly1d(np.polyfit(trend_dates, histo['ssn'][idx], 1))
  axis.plot(trend_dates, poly(trend_dates), label=f'Trend ({TREND_YEARS} years)', linestyle='--',
            color=style.colors[6], linewidth=1)

  axis.plot(predic['time_tag'], pavg, zorder=1, linewidth=1)
  axis.fill_between(predic['time_tag'], predic['smoothed_ssn_min'], predic['smoothed_ssn_max'],
                    label='Predicted', zorder=0, alpha=0.3, linewidth=1)

  axis.set_xlabel('Years')
  axis.set_ylabel('Sun Spot Number')
  axis.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
  axis.xaxis.set_major_locator(mdates.YearLocator(5, month=1, day=1))
  axis.xaxis.set_minor_locator(mdates.YearLocator())
  axis.yaxis.set_major_locator(MultipleLocator(50))
  axis.yaxis.set_minor_locator(MultipleLocator(10))

  legend = axis.legend(loc='upper left')
  for line in legend.get_lines():
    line.set_linewidth(4.0)

  plt.subplots_adjust(bottom=0.15)
  tools.save_plot(plt, filename)
  plt.close()


def main():
  config = Config().get('aindex', {})
  cache_predic = config.get('cache_precictions', '/tmp/ssnpredict.json')
  cache_histo = config.get('cache_history', '/tmp/ssnhist.json')
  cache_time = config.get('cache_time', 86400 * 10)
  target_dir = config.get('target_dir', '/var/www/html')

  parser = argparse.ArgumentParser()
  parser.add_argument('-t', '--target', type=pathlib.Path, default=target_dir,
                      help='Image path')
  opts = parser.parse_args()

  histo = download_history(cache_histo, cache_time)
  predic = download_predictions(cache_predic, cache_time)

  for style in tools.STYLES:
    with plt.style.context(style.style):
      filename = opts.target / f'ssnhist-{style.name}'
      graph(histo, predic, filename, style, 1961)
      if style.name == 'light':
        tools.mk_link(filename, opts.target / 'ssnhist')

  return os.EX_OK


if __name__ == "__main__":
  sys.exit(main())
