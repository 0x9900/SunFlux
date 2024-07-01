#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c)2023 Fred W6BSD
# All rights reserved.
#
#
import logging
import os
from datetime import datetime, timezone

import matplotlib.pyplot as plt
import numpy as np

EXTENTIONS = ('.svgz', '.png')

logger = logging.getLogger('tools')


def remove_outliers(points, low=25, high=95):
  percent_lo = np.percentile(points, low, interpolation='midpoint')
  percent_hi = np.percentile(points, high, interpolation='midpoint')
  iqr = percent_hi - percent_lo
  lower_bound = points <= (percent_lo - 5 * iqr)
  upper_bound = points >= (percent_hi + 5 * iqr)
  points[lower_bound | upper_bound] = np.nan
  return points


def noaa_date(field):
  """Convert the noaa date into a datetime object and make sure the timezone is utc"""
  _date = datetime.strptime(field, '%Y-%m-%dT%H:%M:%S%z')
  _date = _date.replace(tzinfo=timezone.utc)
  return _date


def noaa_date_hook(dct):
  date = noaa_date(dct['time_tag'])
  dct['time_tag'] = date
  return dct


def mk_link(src, dst):
  for ext in EXTENTIONS:
    src_img = src.with_suffix(ext)
    dst_img = dst.with_suffix(ext)
    if dst_img.exists():
      dst_img.unlink()
    os.link(src_img, dst_img)
    logger.info('Link %s ->  %s', src_img, dst_img)


def save_plot(plt, filename):
  if not filename.parent.exists():
    logger.error('[Errno 2] No such file or directory: %s', filename.parent)
    return
  for ext in EXTENTIONS:
    fname = filename.with_suffix(ext)
    try:
      plt.savefig(fname, transparent=False, dpi=100)
      logger.info('Graph "%s" saved', fname)
    except (FileNotFoundError, ValueError) as err:
      logger.error(err)


def set_dark_theme():
  plt.rcParams.update({
    'figure.facecolor': '#050505',
    'axes.facecolor': '#050505',
    'axes.edgecolor': '#eaeaea',
    'axes.labelcolor': '#eaeaea',
    'xtick.color': '#eaeaea',
    'ytick.color': '#eaeaea',
    'grid.color': '#333333',
    'text.color': '#eaeaea',
  })
  return 'dark'


# Function to set the light theme
def set_light_theme():
  plt.rcParams.update({
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'axes.edgecolor': 'black',
    'axes.labelcolor': 'black',
    'xtick.color': 'black',
    'ytick.color': 'black',
    'grid.color': 'gray'
  })
  return 'light'


THEMES = {
  'light': set_light_theme,
  'dark': set_dark_theme,
}
