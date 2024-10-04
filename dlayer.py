#! /usr/bin/env python
# vim:fenc=utf-8
#
# Copyright © 2024 fred <github-fred@hidzz.com>
#
# Distributed under terms of the BSD 3-Clause license.

"""
Generate a world image with the ionosphere D layer absorption
"""

import argparse
import io
import logging
import os
import pathlib
import pickle
import re
import sys
import time
from datetime import datetime, timezone
from urllib.request import urlopen

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from mpl_toolkits.basemap import Basemap

import tools
from config import Config

DRAP_URL = 'https://services.swpc.noaa.gov/text/drap_global_frequencies.txt'
MAX_FREQUENCY = 36

MAP_COLORS = {
  'light': {
    'land': 'wheat',
    'ocean': 'lavender',
    'coastlines': 'brown',
    'grid': 'lightgray',
    'colors': ['lavender', '#2989d8', '#99aaaa', '#ffff00', '#bb0000'],
  },
  'dark': {
    'land': '#000000',
    'ocean': '#0d1522',
    'coastlines': '#e0e0e0',
    'grid': 'lightgray',
    'colors': ['#0d1117', '#2989d8', '#99aaaa', '#ffff00', '#bb0000'],
  },
}

# Silence matplotlib debug messages
logging.getLogger('matplotlib').setLevel(logging.WARNING)


class Drap:
  def __init__(self, cache_path, cache_time):
    self.data = np.array([])
    self.prod_date = None
    self.lat = None
    self.lon = None
    self.xray = None

    cache_name = pathlib.Path(__file__).with_suffix('.pkl').name
    self.cache_file = pathlib.Path(cache_path).joinpath(cache_name)
    self.cache_time = cache_time
    logging.debug('Cache: %s', self.cache_file)

    for key, val in self.get_drap().items():
      setattr(self, key, val)
    self.data[self.data > MAX_FREQUENCY] = MAX_FREQUENCY

  def get_drap(self):
    now = time.time()

    try:
      file_st = os.stat(self.cache_file)
      if now - file_st.st_mtime > self.cache_time:
        raise FileNotFoundError
    except FileNotFoundError:
      self._download_drap()
    return self.read_cache()

  def read_cache(self):
    logging.debug('Read from cache')
    with open(self.cache_file, 'rb') as fd_cache:
      return pickle.load(fd_cache)

  def read_header(self, lines):
    headers = {}
    r_date = re.compile(
      r'# Product Valid.*\s(?P<prod_date>\d+-\d+-\d+\s\d+:\d+\sUTC)|'
      r'#\s+X-RAY Message\s:\s(?P<xray>.*)|'
      r'#\s+Proton Message\s:\s(?P<proton>.*)'
    ).match
    while True:
      pos = lines.tell()
      line = lines.readline().rstrip()
      if match := r_date(line):
        if match.lastgroup == 'prod_date':
          prod_date = match.group(match.lastgroup)
          prod_date = datetime.strptime(prod_date, '%Y-%m-%d %H:%M %Z')
          prod_date.replace(tzinfo=timezone.utc)
          headers['prod_date'] = prod_date
        else:
          headers[match.lastgroup] = match[match.lastgroup]
      elif not line.startswith('#'):
        lines.seek(pos)
        break

    return headers

  def _download_drap(self):
    logging.info('Download from %s', DRAP_URL)
    lat = []
    lon = []
    data = []
    with urlopen(DRAP_URL) as _res:
      encoding = _res.info().get_content_charset('utf-8')
      content = io.StringIO(_res.read().decode(encoding))

    dlayer = self.read_header(content)
    for line in content:
      lon = [float(d) for d in line.split()]
      break
    for line in content:
      if line.startswith('-' * 10):
        break
    for line in content:
      _lat, flux = line.split('|')
      lat.append(float(_lat))
      data.append([float(f) for f in flux.split()])

    dlayer['lon'] = np.array(lon, dtype=np.float16)
    dlayer['lat'] = np.array(lat, dtype=np.float16)
    dlayer['data'] = np.array(data, dtype=np.float16)

    with open(self.cache_file, 'wb') as fd_cache:
      pickle.dump(dlayer, fd_cache)

  def print_info(self, fig):
    fig.text(0.72, .11, f'{self.prod_date.strftime("%a %b %d %Y - %H:%M %Z")}', fontsize=8)
    for nbr, key in enumerate(("proton", "xray")):
      if msg := getattr(self, key):
        fig.text(0.125, 0.12 - (0.03 * nbr), msg, fontsize=8)

  def plot(self, filename, style):
    fig, axgc = plt.subplots(figsize=(10, 5))
    axgc.set_title('DLayer Absorption')
    self.print_info(fig)
    dmap = Basemap(projection='cyl', resolution='c',
                   llcrnrlat=-75, urcrnrlat=89, llcrnrlon=-175, urcrnrlon=175)

    # Draw the data
    lon, lat = np.meshgrid(self.lon, self.lat)
    clevels = np.arange(self.data.min() + 1, MAX_FREQUENCY + 1)
    dmap.contourf(lon, lat, self.data, clevels, vmax=MAX_FREQUENCY,
                  cmap=self.mk_colormap(style))

    self.draw_colorbar(dmap, self.data.max())
    self.draw_elements(dmap, style)
    tools.save_plot(plt, filename)

    plt.close()

  @staticmethod
  def draw_colorbar(fig, fmax=None):
    cbar = fig.colorbar(size="3.5%", pad="2%", format=lambda x, _: f"{int(round(x)):d}")
    cbar.set_label('Affected Frequency (MHz)')
    cbar.set_ticks(np.linspace(1, MAX_FREQUENCY, 6))
    if fmax:
      cbar.ax.arrow(0.1, fmax, 0.6, 0, width=0.03, head_width=0.6, head_length=0.2, fc='k', ec='k')
      lpos = fmax - 1 if fmax > 22 else fmax + .5
      cbar.ax.annotate('Max', xy=(0, lpos), xytext=(0, lpos), fontsize=8)

  @staticmethod
  def draw_elements(fig, style):
    colors = MAP_COLORS[style.name]

    fig.drawparallels([-66.33, -23.5, 0, 23.5, 66.33], linewidth=.5,
                      color=colors['grid'], dashes=[2, 2])
    fig.drawmeridians([-90, 0, 90], linewidth=.5, color=colors['grid'], dashes=[2, 2])
    fig.drawcoastlines(linewidth=.6, color=colors['coastlines'])
    fig.drawlsmask(land_color=colors['land'], ocean_color=colors['ocean'], lakes=False)

  @staticmethod
  def mk_colormap(style):
    colors = MAP_COLORS[style.name]['colors']
    pos = [0.0, 0.2, 0.4, 0.6, 1.0]
    cmap_name = 'my_cmap'
    n_bins = MAX_FREQUENCY
    cmap = LinearSegmentedColormap.from_list(cmap_name, list(zip(pos, colors)), N=n_bins)
    return cmap


def main():
  config = Config()
  cache_path = config.get('dlayer.cache_path', '/tmp')
  cache_time = config.get('dlayer.cache_time', 120)
  target_dir = config.get('dlayer.target_dir', '/var/www/html/d-rap')

  if os.isatty(sys.stdout.fileno()):
    log_file = None
  else:
    log_file = config.get('dlayer.log_filename', '/tmp/dlayer.log')

  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)3d %(levelname)s - %(message)s', datefmt='%x %X',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO')),
    filename=log_file
  )

  parser = argparse.ArgumentParser(description="DLayer absorption graph")
  parser.add_argument('-t', '--target', type=pathlib.Path, default=target_dir,
                      help='Image path')
  opts = parser.parse_args()
  drap = Drap(cache_path, cache_time)

  today = datetime.now(timezone.utc)
  path = opts.target
  try:
    path.mkdir(parents=True, exist_ok=True)
  except FileExistsError as err:
    logging.error(err)
    raise SystemExit(err) from None

  styles = tools.STYLES
  for style in styles:
    with plt.style.context(style.style):
      filename = opts.target.joinpath(f'dlayer-{today.strftime("%Y%m%dT%H%M%S")}-{style.name}')
      drap.plot(filename, style)
      tools.mk_link(filename, opts.target.joinpath(f'latest-{style.name}'))
      if style.name == 'light':
        tools.mk_link(filename, opts.target.joinpath(f'dlayer-{today.strftime("%Y%m%dT%H%M%S")}'))
        tools.mk_link(filename, opts.target.joinpath('latest'))

  return os.EX_OK


if __name__ == "__main__":
  main()
