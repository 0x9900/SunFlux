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
import logging
import os
import pathlib
import pickle
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.request import urlopen

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from mpl_toolkits.basemap import Basemap
from PIL import Image

from config import Config

DRAP_URL = 'https://services.swpc.noaa.gov/text/drap_global_frequencies.txt'


class Drap:
  def __init__(self, cache_path, cache_time):
    parsed_url = urlparse(DRAP_URL)
    cache_file = pathlib.Path(parsed_url.path).stem
    self.cache_file = pathlib.Path(cache_path).joinpath(cache_file + '.pkl')
    self.cache_time = cache_time
    self.lon, self.lat, self.data = self.get_drap()

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
    logging.info('Read from cache')
    with open(self.cache_file, 'rb') as fd_cache:
      return pickle.load(fd_cache)

  def _download_drap(self):
    logging.info('Download from %s', DRAP_URL)
    lat = []
    lon = []
    data = []
    with urlopen(DRAP_URL) as _res:
      encoding = _res.info().get_content_charset('utf-8')
      res = (r.decode(encoding).strip() for r in _res if not r.startswith(b'#'))
      for line in res:
        lon = [float(d) for d in line.split()]
        break
      for line in res:
        if line.startswith('-------'):
          break
      for line in res:
        _lat, flux = line.split('|')
        lat.append(float(_lat))
        data.append([float(f) for f in flux.split()])

    lon = np.array(lon, dtype=np.float16)
    lat = np.array(lat, dtype=np.float16)
    data = np.array(data, dtype=np.float16)

    with open(self.cache_file, 'wb') as fd_cache:
      pickle.dump([lon, lat, data], fd_cache)

  def plot(self, image_path):
    # pylint: disable=too-many-locals
    today = datetime.now(timezone.utc)
    color_map = Drap.mk_colormap()
    fig, axgc = plt.subplots(figsize=(10, 5), facecolor='white')

    dmap = Basemap(projection='cyl', resolution='c',
                   llcrnrlat=-80, urcrnrlat=90, llcrnrlon=-175, urcrnrlon=175)

    # Draw map elements
    dmap.drawcoastlines(linewidth=.6, color='brown')
    dmap.drawlsmask(land_color='#F4A460',ocean_color='aqua',lakes=True)

    lon, lat = np.meshgrid(self.lon, self.lat)
    clevels = np.arange(self.data.min() + 1, self.data.max() + 1, .1)
    dmap.contourf(lon, lat, self.data, clevels, cmap=color_map)
    # dmap.pcolormesh(lon, lat, self.data, cmap=color_map)

    cbar = dmap.colorbar(size="2.5%", pad="2%", format=lambda x, _: f"{int(round(x)):d}")
    cbar.set_label('Frequency (MHz)', weight='bold', size=10)

    axgc.set_title('DLayer Absorption', fontsize=16, fontweight='bold')
    date = today.strftime("%a %b %d %Y - %H:%M %Z")
    fig.text(0.72, .03, f'{date}', fontsize=10)
    fig.text(0.02, .03, f'(c){today.year} W6BSD https://bsdworld.org/', fontsize=10,
             style='italic')

    path = pathlib.Path(image_path)
    try:
      path.mkdir(parents=True, exist_ok=True)
    except FileExistsError as err:
      logging.error(err)
      return None

    name = f'dlayer-{today.strftime("%Y%m%d%H%M")}.png'
    filename = path.joinpath(name)
    fig.savefig(filename, transparent=False, dpi=100)
    logging.info('Dlayer graph "%s" saved', filename)

    plt.close()
    return filename

  @staticmethod
  def mk_colormap():
    colors = ['#f0f0f0', '#2989d8', '#c1614a']
    # colors = ["#5f2372", "yellow", "#e75a1f",]
    pos = [0.0, 0.5, 1.0]
    cmap_name = 'my_cmap'
    n_bins = 24
    cmap = LinearSegmentedColormap.from_list(cmap_name, list(zip(pos, colors)), N=n_bins)
    return cmap


def mk_latest(image_name):
  path = image_name.parents[0]
  latest = path.joinpath('latest.png')
  if latest.exists():
    latest.unlink()
  os.link(image_name, latest)
  logging.info('Lint to %s created', latest)


def mk_thumnail(image_name):
  path = image_name.parents[0]
  image = Image.open(image_name)
  image = image.convert('RGB')
  image.thumbnail((600, 250))
  for fmt in ('jpg', 'png', 'webp'):
    try:
      tn_file = path.joinpath(f'tn_latest.{fmt}')
      image.save(tn_file, format=fmt if fmt != 'jpg' else 'jpeg', dpi=(100, 100))
      logging.info('Thumbnail "%s" saved', tn_file)
    except ValueError as err:
      logging.warning(err)


def main():
  config = Config()

  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s', datefmt='%x %X',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )

  parser = argparse.ArgumentParser(description="DLayer absorption graph")
  parser.add_argument('-t', '--target', default='/var/tmp/drap', help='Image path')
  opts = parser.parse_args()

  cache_path = config.get('dlayer.cache_path', '/tmp')
  cache_time = config.get('dlayer.cache_time', 900)
  drap = Drap(cache_path, cache_time)
  image_name = drap.plot(opts.target)
  mk_latest(image_name)
  mk_thumnail(image_name)


if __name__ == "__main__":
  main()
