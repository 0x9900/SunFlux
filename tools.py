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
import pathlib
import re
import sqlite3
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)


EXTENTIONS = ('.svgz', '.png')

WWV_CONDITIONS = "SELECT conditions FROM wwv WHERE time > ? ORDER BY time DESC LIMIT 1"

logger = logging.getLogger('tools')


COLOR_MAPS = {
  'dark': [
    '#008585',
    '#74a892',
    '#fbf2c4',
    '#e5c185',
    '#e0a278',
    '#db836b',
    '#c7522a',
    '#642915',
    '#32150b',
  ],
  'light': [
    '#ffd380',
    '#ffa600',
    '#ff8531',
    '#ff6361',
    '#bc5090',
    '#8a508f',
    '#2c4875',
    '#003f5c',
    '#00202e',
  ],
}


def get_conditions(config):
  db_name = config['db_name']
  start_time = datetime.now(timezone.utc) - timedelta(days=1)
  conn = sqlite3.connect(db_name, timeout=5, detect_types=sqlite3.PARSE_DECLTYPES)
  with conn:
    curs = conn.cursor()
    result = curs.execute(WWV_CONDITIONS, (start_time,)).fetchone()
    try:
      conditions = result[0]
    except TypeError:
      return None
  if re.match(r'(No Storm.*){2}', conditions):
    return None
  # cleanup the string and return
  return re.sub(r'[^\x20-\x7E]', '', conditions).strip()


def mk_colormap(map_name, nb_colors=8):
  reverse = False
  if map_name[0] == '-':
    map_name = map_name[1:]
    reverse = True

  cmap = plt.get_cmap(map_name)
  if cmap.N > 32:
    indices = np.linspace(0, 1, nb_colors)
    colors = cmap(indices)
  else:
    colors = cmap.colors[:nb_colors]
  hex_colors = [mcolors.rgb2hex(color) for color in colors]
  return hex_colors[::-1] if reverse else hex_colors


@dataclass(frozen=True, slots=True)
class GraphStyle:
  name: str
  style: str
  cmap: str | None
  top: str
  bottom: str
  colors: list | None = None

  def __post_init__(self):
    home = pathlib.Path.home().joinpath('.local')
    style_path = [pathlib.Path(p).absolute() for p in ('.', home, '/var/tmp')]
    for path in style_path:
      stylefile = path.joinpath(self.style)
      if stylefile.exists():
        object.__setattr__(self, 'style', str(stylefile))
        break
    else:
      raise SystemExit('Style: {self.style} not found')

    if self.cmap in COLOR_MAPS:
      object.__setattr__(self, 'colors', COLOR_MAPS[self.cmap])
    else:
      try:
        object.__setattr__(self, 'colors', mk_colormap(self.cmap))
      except ValueError:
        logger.error('"%s" is not a valid colormap.', self.cmap)
        raise SystemExit from None


STYLES = [
  GraphStyle('light', 'light.mplstyle', 'light', '#82746C', '#5F9EA0'),
  GraphStyle('dark', 'dark.mplstyle', 'dark',  '#778899', '#2F4F4F'),
]


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


def save_plot(plot, filename, extentions=EXTENTIONS):
  fig = plot.gcf()
  today = datetime.now(timezone.utc).strftime('%Y')
  fig.text(0.01, 0.02, f'\xa9 W6BSD {today} https://bsdworld.org/', fontsize=8, style='italic')
  if not filename.parent.exists():
    logger.error('[Errno 2] No such file or directory: %s', filename.parent)
    return

  metadata = {'Description': f"{filename.stem} - Solar activity https://bsdworld.org/"}
  for ext in extentions:
    fname = filename.with_suffix(ext)
    try:
      if ext in ['.svg', '.svgz', '.png']:
        plot.savefig(fname, transparent=False, dpi=100, metadata=metadata)
      else:
        plot.savefig(fname, transparent=False, dpi=100)
      logger.info('Graph "%s" saved', fname)
    except (FileNotFoundError, ValueError) as err:
      logger.error(err)

#
