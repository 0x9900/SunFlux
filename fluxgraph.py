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
import pickle
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

import adapters
import tools
from config import Config

NB_DAYS = 92
TREND_WK = 3
MIN_TICKS = 55

WWV_REQUEST = "SELECT wwv.time, wwv.SFI FROM wwv WHERE wwv.time > ?"

NOAA_URL = 'https://services.swpc.noaa.gov/json/f107_cm_flux.json'

logging.basicConfig(
  format='%(asctime)s %(levelname)s - %(name)s:%(lineno)3d - %(message)s', datefmt='%x %X',
  level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
)
logger = logging.getLogger('fluxgraph')


def moving_average(data, window=5):
  average = np.convolve(data, np.ones(window), 'valid') / window
  for _ in range(window - 1):
    average = np.insert(average, 0, np.nan)
  return average


def download_flux(cache_file):
  data = {}
  with urllib.request.urlopen(NOAA_URL) as res:
    encoding = res.info().get_content_charset('utf-8')
    _data = res.read()
    data = json.loads(_data.decode(encoding))

  flux_data = {}
  for elem in data:
    try:
      t_tag = tools.noaa_date(elem['time_tag'] + 'Z')
      flux_data[t_tag] = float(elem['flux'])
    except ValueError as err:
      logger.warning('%s - Element: %s', err, elem)

  with open(cache_file, 'wb') as cfd:
    pickle.dump(flux_data, cfd)


def get_noaa_flux(config):
  cache_file = config.get('cache_file', '/tmp/aindex-noaa.pkl')
  cache_time = config.get('cache_time', 3600 * 2)
  days = config.get('nb_days', NB_DAYS)
  now = time.time()
  start_date = datetime.now(timezone.utc) - timedelta(days=days)

  try:
    filest = os.stat(cache_file)
    if now - filest.st_mtime > cache_time:
      raise FileNotFoundError
  except FileNotFoundError:
    download_flux(cache_file)

  data = {}
  with open(cache_file, 'rb') as cfd:
    _data = pickle.load(cfd)
    for date, flux in _data.items():
      if date >= start_date:
        data[date] = flux
  return data


def get_flux(config):
  db_name = config.get('db_name')
  days = config.get('nb_days', NB_DAYS)
  start_date = datetime.now(timezone.utc) - timedelta(days=days)
  data = {}

  conn = sqlite3.connect(db_name, timeout=5,
                         detect_types=sqlite3.PARSE_DECLTYPES)
  with conn:
    curs = conn.cursor()
    results = curs.execute(WWV_REQUEST, (start_date,))
    for elem in results:
      date = elem[0]
      date = date.replace(tzinfo=timezone.utc)
      data[date] = float(elem[1])

  return data


def graph(data, filename, style, trend_week=3):
  # pylint: disable=invalid-name, too-many-locals
  trend_days = trend_week * 7
  arr = np.array(data)
  dstart = mdates.date2num(data[-1][0] - timedelta(days=trend_days))
  arr[:, 0] = mdates.date2num(arr[:, 0])
  x, y = arr[:, 0].astype(np.float64), arr[:, 1].astype(np.int32)
  idx = x[:] > dstart
  poly = np.poly1d(np.polyfit(x[idx], y[idx], 1))
  avg = moving_average(arr[:, 1], 7)

  date = datetime.now(timezone.utc).strftime('%Y/%m/%d %H:%M UTC')
  fig = plt.figure(figsize=(12, 5))
  fig.suptitle('Daily 10cm Flux Index')
  axgc = plt.gca()
  axgc.plot(x, y, linewidth=1, label='Flux', color=style.colors[4])
  mave, = axgc.plot(x, avg, linewidth=1.5, linestyle=":", label='Daily Average',
                    color=style.colors[5])
  trend, = axgc.plot(x[idx], poly(x[idx]), label=f'Trend ({trend_week} weeks)', linestyle='--',
                     color=style.colors[6], linewidth=1)
  axgc.tick_params(labelsize=10)

  for pos in set([y.argmax(), y.argmin(), x.size - 1]):
    xytext = (20, 20) if pos == x.size - 1 else (20, -20)
    plt.annotate(f"{int(y[pos]):d}", (x[pos], y[pos]), textcoords="offset points", xytext=xytext,
                 ha='center', fontsize=10, color=style.colors[6],
                 arrowprops={'arrowstyle': 'wedge', 'color': style.colors[4]},
                 bbox={'boxstyle': 'square,pad=0.2', 'fc': 'white'})

  loc = mdates.DayLocator(interval=10)
  axgc.xaxis.set_major_formatter(mdates.DateFormatter('%a, %b %d UTC'))
  axgc.xaxis.set_major_locator(loc)
  axgc.xaxis.set_minor_locator(mdates.DayLocator())
  axgc.set_ylabel('SFU at 2800 MHz')
  # axgc.set_ylim([MIN_TICKS, y.max() * 1.15])

  ticks = np.array([MIN_TICKS, 70])
  ticks = np.append(ticks, np.arange(90, int(y.max() * 1.15), 20))
  axgc.set_yticks(ticks)

  zone1 = axgc.axhspan(90, round(axgc.axis()[-1]), facecolor=style.colors[0],
                       alpha=0.3, label='Good')
  zone2 = axgc.axhspan(70, 90, facecolor=style.colors[1], alpha=0.3, label='Ok')
  zone3 = axgc.axhspan(MIN_TICKS, 70, facecolor=style.colors[2], alpha=0.3, label='Bad')

  trend_legend = axgc.legend(handles=[trend, mave], loc='lower left')
  axgc.add_artist(trend_legend)
  axgc.legend(handles=[zone1, zone2, zone3], loc="upper left")
  axgc.margins(x=.015)

  fig.autofmt_xdate(rotation=10, ha="center")
  fig.text(0.01, 0.02, f'SunFlux (c)W6BSD {date}', fontsize=8, style='italic')

  tools.save_plot(plt, filename)
  plt.close()


def main():
  adapters.install_adapters()
  logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))
  config = Config().get('fluxgraph', {})
  target_dir = config.get('target_dir', '/var/www/html')

  parser = argparse.ArgumentParser()
  parser.add_argument('-D', '--days', default=config.get('nb_days', NB_DAYS), type=int,
                      help='Number of days to graph [Default: %(default)s]')
  parser.add_argument('-T', '--trend', default=config.get('trend_weeks', TREND_WK), type=int,
                      help='Number of trend days [Default: %(default)s]')
  parser.add_argument('-t', '--target', type=pathlib.Path, default=target_dir,
                      help='Image path')
  opts = parser.parse_args()

  config['nb_days'] = opts.days
  data = get_flux(config)
  data.update(get_noaa_flux(config))
  data = sorted(list(data.items()))

  if not data:
    logger.warning('No data collected')
    return os.EX_DATAERR

  logger.debug('Dataset size: %d', len(data))
  styles = tools.STYLES
  for style in styles:
    with plt.style.context(style.style):
      filename = opts.target.joinpath(f'flux-{style.name}')
      graph(data, filename, style, opts.trend)
      if style.name == 'light':
        tools.mk_link(filename, opts.target.joinpath('flux'))

  return os.EX_OK


if __name__ == "__main__":
  sys.exit(main())
