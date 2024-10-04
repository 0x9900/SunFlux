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
from dataclasses import dataclass
from datetime import datetime, timezone

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np

EXTENTIONS = ('.svgz', '.png')

logger = logging.getLogger('tools')


COLOR_MAPS = {
  'dark': [
    '#76c7c0',  # (Soft Teal)
    '#ffcc66',  # (Warm Amber)
    '#99cc99',  # (Muted Green)
    '#ff6666',  # (Soft Red)
    '#6699cc',  # (Soft Blue)
    '#c594c5',  # (Muted Purple)
    '#e6b3b3',  # (Dusty Rose)
    '#999999',  # (Muted Gray)
  ],
  'light': [
    '#1f77b4',
    '#ff7f0e',
    '#2ca02c',
    '#d62728',
    '#9467bd',
    '#8c564b',
    '#e377c2',
    '#7f7f7f',
  ],
}


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
  arrows: list
  colors: list | None = None

  def __post_init__(self):
    style_path = [pathlib.Path(p).absolute() for p in ('.', '/var/tmp')]
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
      object.__setattr__(self, 'colors', mk_colormap(self.cmap))


STYLES = [
  GraphStyle('light', 'light.mplstyle', 'light', ['#444444', '#4169e1']),
  GraphStyle('dark', 'dark.mplstyle', 'dark',  ['#81b1d2', '#bc82bd']),
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


def save_plot(plt, filename):
  fig = plt.gcf()
  today = datetime.now(timezone.utc).strftime('%Y/%m/%d %H:%M UTC')
  fig.text(0.01, 0.02, f'SunFlux (c) W6BSD {today}', fontsize=8, style='italic')
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

#
