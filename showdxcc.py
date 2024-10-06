#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c)2022-2023 Fred W6BSD
# All rights reserved.
#
#

import argparse
import logging
import os
import pathlib
import sqlite3
import sys
from collections import deque
from datetime import datetime, timedelta, timezone

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image

import adapters
import tools
from config import Config

CONTINENTS = ['AF', 'AS', 'EU', 'NA', 'OC', 'SA']
BANDS = [6, 10, 12, 15, 17, 20, 30, 40, 60, 80, 160]


class ShowDXCC:

  def __init__(self, config, zone_name, zone, date=None):
    self.config = config
    self.date = date if date else datetime.now(timezone.utc)
    self.today = self.date.strftime('%Y/%m/%d %H:%M %Z')
    self.data = []
    self.zone_name = zone_name
    try:
      self.zone = int(zone)
    except ValueError:
      self.zone = f'"{zone}"'

    try:
      self.zone_label = {
        'continent': ('de_cont', 'to_cont'),
        'ituzone': ('de_ituzone', 'to_ituzone'),
        'cqzone': ('de_cqzone', 'to_cqzone'),
      }[zone_name]
    except KeyError:
      raise SystemError(f'Zone {zone_name} error') from None

  def is_data(self):
    return np.any(self.data)

  @staticmethod
  def center(continents, label):
    deq = deque(continents)
    deq.rotate(- 1 - (len(deq) // 2 + deq.index(label)))
    return list(deq)

  def get_dxcc(self, delta=1):
    start_date = self.date - timedelta(hours=delta, minutes=0)
    end_date = self.date
    request = (f"SELECT band, de_cont, to_cont, COUNT(*) FROM dxspot WHERE band >= 6 "
               f"AND ({self.zone_label[0]} = {self.zone} OR {self.zone_label[1]} = {self.zone}) "
               f"AND time > {start_date.timestamp()} "
               f"AND time <= {end_date.timestamp()} "
               "GROUP BY band, to_cont;")
    conn = sqlite3.connect(self.config['showdxcc.db_name'], timeout=5,
                           detect_types=sqlite3.PARSE_DECLTYPES)
    logging.debug(request)
    with conn:
      curs = conn.cursor()
      results = curs.execute(request).fetchall()

    self.data = np.zeros((len(CONTINENTS), len(BANDS)), dtype=int)
    for band, _, to_continent, count in results:
      _x = CONTINENTS.index(to_continent)
      _y = BANDS.index(band)
      self.data[_x, _y] = count

  def graph(self, filename):
    dmax = np.max(self.data)
    color_map = ShowDXCC.mk_colormap()  # self.config.get('showdxcc.color_map', 'PRGn')
    fig, axgc = plt.subplots(figsize=(12, 8))

    # axgc.set_facecolor('#001155')
    # Show all ticks and label them with the respective list entries
    plt.xticks(np.arange(len(BANDS)), labels=BANDS)
    plt.xlabel("Bands")
    plt.yticks(np.arange(len(CONTINENTS)), labels=CONTINENTS)
    plt.ylabel("Destination")

    timage = axgc.imshow(self.data, cmap=color_map)
    axgc.imshow(self.data, cmap=color_map,
                interpolation=self.config.get('showdxcc.interleave', 'gaussian'))

    axgc.set_aspect(aspect=1)
    axgc.tick_params(top=True, bottom=True, labeltop=True, labelbottom=True)

    cbar = axgc.figure.colorbar(timage, ax=axgc, shrink=0.69, aspect=15, fraction=0.09,
                                pad=0.02, ticks=[0, dmax / 2, dmax])
    cbar.ax.set_yticklabels(['low', 'med', 'high'])

    # Loop over data dimensions and create text annotations.
    # threshold = np.percentile(self.data, 70)
    # for i, j in product(range(len(CONTINENTS)), range(len(BANDS))):
    #   if self.data[i, j] < 1:
    #     continue
    #   color = 'white' if self.data[i, j] < threshold else 'black'
    #   axgc.text(j, i, self.data[i, j], ha="center", va="center", color=color)

    axgc.grid(None)
    zone = self.zone.strip('"')
    axgc.set_title(f"HF Propagation from {self.zone_name} = {zone}", y=1.1)
    fig.text(0.72, .92, f'{self.date.strftime("%a %b %d %Y - %H:%M %Z")}')
    fig.tight_layout()
    tools.save_plot(plt, filename, ('.png',))

  @staticmethod
  def mk_colormap():
    colors = [(.0, '#001155'), (.1, '#99aaaa'), (.3, '#ffff00'), (1, '#ff0000')]
    cmap_name = 'my_cmap'
    n_bins = 28
    cmap = LinearSegmentedColormap.from_list(cmap_name, colors, N=n_bins)
    cmap.set_bad(colors[0][1], 1.)
    return cmap


def type_date(parg):
  if parg == 'now':
    date = datetime.now(timezone.utc)
    date = date.replace(second=0, microsecond=0)
    return date

  if len(parg) != 12:
    raise argparse.ArgumentTypeError('The date format should be YYYYMMDDHHMM') from None

  try:
    date = datetime.strptime(parg, '%Y%m%d%H%M')
    date = date.replace(tzinfo=timezone.utc)
  except ValueError:
    raise argparse.ArgumentTypeError from None
  return date


def create_link(filename, target):
  if os.path.exists(target):
    os.unlink(target)
  os.link(filename, target)
  logging.info('Link to "%s" created', target)


def webp(filename, theme_name):
  webpname = f'latest-{theme_name}'
  path = filename.parent
  webpfile = path.joinpath(f'{webpname}.webp')
  image = Image.open(filename)
  image = image.resize((800, 530))
  image.save(webpfile, format='webp')
  logging.info('Image "%s" created', webpfile)
  if theme_name == 'light':
    create_link(webpfile, path.joinpath('latest.png'))


def mk_thumbnail(filename, theme_name):
  path = filename.parent
  image = Image.open(filename)
  image.thumbnail((600, 400))
  for fmt in ('png', 'webp'):
    try:
      tn_file = path.joinpath(f'tn_latest-{theme_name}.{fmt}')
      image.save(tn_file, format=fmt, dpi=(100, 100))
      logging.info('Thumbnail "%s" created', tn_file)
    except ValueError as err:
      logging.error(err)

    if theme_name == 'light':
      create_link(tn_file, path.joinpath(f'tn_latest.{fmt}'))


def save_graphs(dxcc, target_dir, zone_name, zone, now):
  name_tmpl = f'dxcc-{zone_name}{zone}-{now}-{{name}}.png'
  styles = tools.STYLES
  for style in styles:
    with plt.style.context(style.style):
      filename = target_dir.joinpath(name_tmpl.format(name=style.name))
      dxcc.graph(filename)
      webp(filename, style.name)
      mk_thumbnail(filename, style.name)
      create_link(filename, target_dir.joinpath(f'latest-{style.name}.png'))
      if style.name == 'light':
        create_link(filename, target_dir.joinpath(f'dxcc-{zone_name}{zone}-{now}.png'))
        create_link(filename, target_dir.joinpath('latest.png'))


def find_zone(opts, *zone_names):
  for zone_name in zone_names:
    zone = str(getattr(opts, zone_name) or '')
    if zone:
      return zone_name, zone
  raise ValueError(f'Zone "{zone}" not found')


def main():
  adapters.install_adapters()
  config = Config()
  filename = None

  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s', datefmt='%x %X',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )

  parser = argparse.ArgumentParser(description="Graph dxcc trafic")
  parser.add_argument("-d", "--date", type=type_date, default='now',
                      help="Graph date [YYYYMMDDHHMM]")
  parser.add_argument("-D", "--delta", type=int, default=1,
                      help="Number of hours [default: %(default)d]")
  parser.add_argument("-L", "--no-link", action="store_true", default=False,
                      help="Update the link \"latest\"")
  parser.add_argument("-T", "--thumbnail", action="store_true", default=False,
                      help="Create a thumbnail file named \"tn_latest.png\"")
  z_group = parser.add_mutually_exclusive_group(required=True)
  z_group.add_argument("-c", "--continent", choices=CONTINENTS, help="Continent")
  z_group.add_argument("-I", "--ituzone", type=int, help="itu zone")
  z_group.add_argument("-C", "--cqzone", type=int, help="cq zone")
  parser.add_argument('args', nargs="*")
  opts = parser.parse_args()

  zone_name, zone = find_zone(opts, 'continent', 'ituzone', 'cqzone')
  showdxcc = ShowDXCC(config, zone_name, zone, opts.date)
  showdxcc.get_dxcc(opts.delta)

  if opts.args:
    filename = pathlib.Path(opts.args.pop())
    showdxcc.graph(filename)
    return os.EX_OK

  now = opts.date.strftime("%Y%m%dT%H%M%S")
  target_root = pathlib.Path(config.get('showdxcc.target_dir', '/var/tmp/dxcc'))
  target_dir = target_root.joinpath(zone_name, zone)
  target_dir.mkdir(parents=True, exist_ok=True)
  save_graphs(showdxcc, target_dir, zone_name, zone, now)

  return os.EX_OK


if __name__ == "__main__":
  sys.exit(main())
