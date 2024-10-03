#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c)2022-2023 Fred W6BSD
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
from datetime import datetime, timedelta, timezone
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
  for item in data:
    date = datetime.strptime(item['time-tag'], '%Y-%m')
    item['time-tag'] = date.replace(tzinfo=timezone.utc)
  return data


def _predictions_cache(cache_file):
  with open(cache_file, 'r', encoding='ASCII') as cfd:
    data = json.load(cfd)
  for item in data:
    date = datetime.strptime(item['time-tag'], '%Y-%m')
    item['time-tag'] = date.replace(tzinfo=timezone.utc)
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
  start_date = datetime(year, 1, 1, tzinfo=timezone.utc)
  end_date = datetime.now(timezone.utc) + timedelta(days=365 * 12)
  last_date = histo[-1]['time-tag'].strftime("%m-%Y")

  xdates = np.array([d['time-tag'] for d in histo if d['time-tag'] > start_date])
  yvals = np.array([d['ssn'] for d in histo if d['time-tag'] > start_date])
  mavg = moving_average(yvals)

  pdates = np.array([d['time-tag'] for d in predic if d['time-tag'] < end_date])
  lvals = np.array([d['smoothed_ssn_min'] for d in predic if d['time-tag'] < end_date])
  hvals = np.array([d['smoothed_ssn_max'] for d in predic if d['time-tag'] < end_date])
  pavg = np.array([d['ssn'] for d in predic if d['time-tag'] < end_date])

  today = datetime.now(timezone.utc).strftime('%Y/%m/%d %H:%M %Z')
  fig = plt.figure(figsize=(12, 5))
  fig.suptitle(f'SunSpot Numbers from {year} to {last_date}')
  fig.text(0.01, 0.02, f'SunFlux (c)W6BSD {today}', fontsize=8, style='italic')

  axis = plt.gca()
  axis.plot(xdates, yvals, label='Sun Spots', zorder=4, color=style.colors[0], linewidth=0.75)
  axis.plot(xdates, mavg, label='Average', zorder=5, color=style.colors[1], linewidth=1.5)
  axis.fill_between(pdates, lvals, hvals, label='Predicted', zorder=0, alpha=0.3, linewidth=1,
                    facecolor=style.colors[2])
  axis.plot(pdates, pavg, zorder=4, color=style.colors[1], linewidth=1.5)

  axis.axhline(y=yvals.mean(), label='All time mean', zorder=1, color=style.colors[7],
               linewidth=1, linestyle='dashed')

  axis.set_xlabel('Years')
  axis.set_ylabel('Sun Spot Number')
  axis.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
  axis.xaxis.set_major_locator(mdates.YearLocator(5, month=1, day=1))
  axis.xaxis.set_minor_locator(mdates.YearLocator())
  axis.yaxis.set_major_locator(MultipleLocator(25))
  axis.yaxis.set_minor_locator(MultipleLocator(5))

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
      filename = opts.target.joinpath(f'ssnhist-{style.name}')
      graph(histo, predic, filename, style, 1961)
      if style.name == 'light':
        tools.mk_link(filename, opts.target.joinpath('ssnhist'))

  return os.EX_OK


if __name__ == "__main__":
  sys.exit(main())
