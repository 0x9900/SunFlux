#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c)2022-2025 Fred W6BSD
# All rights reserved.
#
#

import argparse
import logging
import os
import pathlib
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from mpl_toolkits.axes_grid1 import make_axes_locatable
from PIL import Image

import adapters
import tools
from config import Config

CONTINENTS = ['AF', 'AS', 'EU', 'NA', 'OC', 'SA']
BANDS = [6, 10, 12, 15, 17, 20, 30, 40, 60, 80, 160]
CONTINENT_IDX = {name: idx for idx, name in enumerate(CONTINENTS)}
BAND_IDX = {band: idx for idx, band in enumerate(BANDS)}

# zone name -> (source column, destination column)
ZONE_COLUMNS = {
  'continent': ('de_cont', 'to_cont'),
  'ituzone': ('de_ituzone', 'to_ituzone'),
  'cqzone': ('de_cqzone', 'to_cqzone'),
}

FIGSIZE = (9, 5)

COLORMAP_COLORS = [(.0, '#001155'), (.1, '#99aaaa'), (.3, '#ffff00'), (1, '#ff0000')]

QUERY = """
  SELECT band, de_cont, to_cont, COUNT(*) FROM dxspot
  WHERE band BETWEEN 6 AND 160
    AND ({de_col} = :zone OR {to_col} = :zone)
    AND time > :start AND time <= :end
  GROUP BY band, to_cont;
"""


def mk_colormap():
  cmap = LinearSegmentedColormap.from_list('my_cmap', COLORMAP_COLORS, N=28)
  cmap.set_bad(COLORMAP_COLORS[0][1], 1.)
  return cmap


class ShowDXCC:

  def __init__(self, config, zone_name, zone, date=None):
    if zone_name not in ZONE_COLUMNS:
      raise ValueError(f'Unknown zone type: {zone_name}')

    self.config = config
    self.date = date or datetime.now(timezone.utc)
    self.zone_name = zone_name
    self.zone = zone if zone_name == 'continent' else int(zone)
    self.data = np.zeros((len(CONTINENTS), len(BANDS)), dtype=int)

  def get_dxcc(self, delta=1):
    de_col, to_col = ZONE_COLUMNS[self.zone_name]  # fixed names, safe to format in
    query = QUERY.format(de_col=de_col, to_col=to_col)
    params = {
      'zone': self.zone,
      'start': (self.date - timedelta(hours=delta)).timestamp(),
      'end': self.date.timestamp(),
    }
    logging.debug('%s %s', query, params)

    with closing(sqlite3.connect(self.config['showdxcc.db_name'], timeout=5,
                                 detect_types=sqlite3.PARSE_DECLTYPES)) as conn:
      results = conn.execute(query, params).fetchall()

    self.data = np.zeros((len(CONTINENTS), len(BANDS)), dtype=int)
    for band, de_cont, to_cont, count in results:
      try:
        row, col = CONTINENT_IDX[to_cont], BAND_IDX[band]
      except KeyError:
        logging.debug('Skipping unknown band/continent: %s / %s', band, to_cont)
        continue
      self.data[row, col] = count if de_cont == to_cont else count * 1.25

  def graph(self, filename):
    # Fixed scale: with all-zero data matplotlib would otherwise widen the degenerate
    # 0..0 range around 0, which maps empty cells to the middle of the colormap.
    dmax = max(np.max(self.data), 1)
    fig, axgc = plt.subplots(figsize=FIGSIZE)

    axgc.set_xticks(np.arange(len(BANDS)), labels=BANDS, fontsize=11)
    axgc.set_yticks(np.arange(len(CONTINENTS)), labels=CONTINENTS, fontsize=11)
    axgc.set_xlabel("Bands")
    axgc.set_ylabel("Destination")

    image = axgc.imshow(self.data, cmap=mk_colormap(), vmin=0, vmax=dmax,
                        interpolation=self.config.get('showdxcc.interleave', 'gaussian'))
    axgc.tick_params(top=True, bottom=True, labeltop=True, labelbottom=True)
    axgc.grid(which='major', linestyle='-', color='darkgray', alpha=.5, linewidth=.5)

    # The colorbar gets its own axes glued to the right of the plot, so its height
    # always matches the plot whatever the figure size is.
    cax = make_axes_locatable(axgc).append_axes('right', size='3%', pad=0.15)
    cbar = fig.colorbar(image, cax=cax, ticks=[0, dmax / 2, dmax])
    cbar.ax.set_yticklabels(['low', 'med', 'high'])

    # Title on the left, date on the right, both above the top tick labels
    axgc.set_title(f"HF Band Activity from {self.zone_name} = {self.zone}", loc='left', pad=8,
                   fontsize=14)
    axgc.set_title(self.date.strftime("%a %b %d %Y - %H:%M %Z"), loc='right', pad=8,
                   fontsize='small')
    fig.tight_layout()
    tools.save_plot(plt, filename, ('.png',))
    plt.close(fig)


def type_date(value):
  if value == 'now':
    return datetime.now(timezone.utc).replace(second=0, microsecond=0)
  try:
    if len(value) != 12:
      raise ValueError(value)
    return datetime.strptime(value, '%Y%m%d%H%M').replace(tzinfo=timezone.utc)
  except ValueError:
    raise argparse.ArgumentTypeError('The date format should be YYYYMMDDHHMM') from None


def create_link(filename, target):
  pathlib.Path(target).unlink(missing_ok=True)
  os.link(filename, target)
  logging.info('Link to "%s" created', target)


def make_webp(filename, theme_name):
  webp_file = filename.parent / f'latest-{theme_name}.webp'
  with Image.open(filename) as image:
    width, height = image.size
    image.resize((800, round(800 * height / width))).save(webp_file, format='webp')
  logging.info('Image "%s" created', webp_file)


def make_thumbnails(filename, theme_name):
  path = filename.parent
  with Image.open(filename) as image:
    image.thumbnail((600, 400))
    for fmt in ('png', 'webp'):
      tn_file = path / f'tn_latest-{theme_name}.{fmt}'
      try:
        image.save(tn_file, format=fmt, dpi=(100, 100))
      except ValueError as err:
        logging.error(err)
        continue
      logging.info('Thumbnail "%s" created', tn_file)
      if theme_name == 'light':
        create_link(tn_file, path / f'tn_latest.{fmt}')


def save_graphs(dxcc, target_dir, zone_name, zone, now):
  basename = f'dxcc-{zone_name}{zone}-{now}'
  for style in tools.STYLES:
    with plt.style.context(style.style):
      filename = target_dir / f'{basename}-{style.name}.png'
      dxcc.graph(filename)
      make_webp(filename, style.name)
      make_thumbnails(filename, style.name)
      create_link(filename, target_dir / f'latest-{style.name}.png')
      if style.name == 'light':
        create_link(filename, target_dir / f'{basename}.png')
        create_link(filename, target_dir / 'latest.png')


def find_zone(opts, *zone_names):
  for zone_name in zone_names:
    zone = getattr(opts, zone_name)
    if zone is not None:  # zone 0 is a valid value
      return zone_name, str(zone)
  raise ValueError('No zone specified')


def parse_args():
  parser = argparse.ArgumentParser(description="Graph dxcc traffic")
  parser.add_argument("-d", "--date", type=type_date, default='now',
                      help="Graph date [YYYYMMDDHHMM]")
  parser.add_argument("-D", "--delta", type=int, default=1,
                      help="Number of hours [default: %(default)d]")
  # NOTE: -L and -T are parsed but not used anywhere
  parser.add_argument("-L", "--no-link", action="store_true", default=False,
                      help="Update the link \"latest\"")
  parser.add_argument("-T", "--thumbnail", action="store_true", default=False,
                      help="Create a thumbnail file named \"tn_latest.png\"")
  z_group = parser.add_mutually_exclusive_group(required=True)
  z_group.add_argument("-c", "--continent", choices=CONTINENTS, help="Continent")
  z_group.add_argument("-I", "--ituzone", type=int, help="itu zone")
  z_group.add_argument("-C", "--cqzone", type=int, help="cq zone")
  parser.add_argument('args', nargs="*")
  return parser.parse_args()


def main():
  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s', datefmt='%x %X',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )
  adapters.install_adapters()
  config = Config()
  opts = parse_args()

  zone_name, zone = find_zone(opts, 'continent', 'ituzone', 'cqzone')
  showdxcc = ShowDXCC(config, zone_name, zone, opts.date)
  showdxcc.get_dxcc(opts.delta)

  if opts.args:
    showdxcc.graph(pathlib.Path(opts.args[-1]))
    return os.EX_OK

  now = opts.date.strftime("%Y%m%dT%H%M%S")
  target_root = pathlib.Path(config.get('showdxcc.target_dir', '/var/tmp/dxcc'))
  target_dir = target_root / zone_name / zone
  target_dir.mkdir(parents=True, exist_ok=True)
  save_graphs(showdxcc, target_dir, zone_name, zone, now)
  return os.EX_OK


if __name__ == "__main__":
  sys.exit(main())
