#!/usr/bin/env python
#

import logging
import os
import sqlite3
import sys

from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import numpy as np

from config import Config

CONTINENTS = ['AF', 'AS', 'EU', 'NA', 'OC', 'SA']
BANDS = [6, 10, 12, 15, 17, 20, 30, 40, 60, 80, 160]

REQUEST = """
SELECT band, de_cont, to_cont, COUNT(*)
FROM dxspot
WHERE band >= 6 AND de_cont == ? AND to_cont != '' AND time > ?
GROUP BY band, to_cont;
"""

def get_dxcc(config, continent, filename):
  # pylint: disable=too-many-locals
  color_map = config.get('showdxcc.color_map', 'PRGn')
  dxcc = CONTINENTS
  now = datetime.utcnow()
  time_span = now - timedelta(hours=1, minutes=0)
  conn = sqlite3.connect(
    config['showdxcc.db_name'],
    timeout=5,
    detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES
  )

  with conn:
    curs = conn.cursor()
    results = curs.execute(REQUEST, (continent, time_span,)).fetchall()

  data = np.zeros((len(dxcc), len(BANDS)), dtype=int)
  for band, _, to_continent, count in results:
    x = dxcc.index(to_continent)
    y = BANDS.index(band)
    data[x, y] = count

  facecolor = 'white' if 6 < now.hour <= 18 else 'gray'
  fig, axgc = plt.subplots(figsize=(12,8), facecolor=facecolor)

  # Show all ticks and label them with the respective list entries
  plt.xticks(np.arange(len(BANDS)), labels=BANDS, fontsize=14)
  plt.xlabel("Bands", fontsize=14)
  plt.yticks(np.arange(len(dxcc)), labels=dxcc, fontsize=14)
  plt.ylabel("DX Continent", fontsize=14)

  image = axgc.imshow(
    data, cmap=color_map, interpolation=config.get('showdxcc.interleave', 'gaussian')
  )
  axgc.set_aspect(aspect=1)
  axgc.tick_params(top=True, bottom=True, labeltop=True, labelbottom=True)

  cbar = axgc.figure.colorbar(image, ax=axgc)
  cbar.ax.set_ylabel("Number of contacts for the last hour",
                     rotation=-90, va="bottom")

  # Loop over data dimensions and create text annotations.
  threshold = np.percentile(data, 96)
  for i in range(len(dxcc)):
    for j in range(len(BANDS)):
      if data[i, j] < 1:
        continue
      color = 'firebrick' if data[i, j] > threshold else 'lime'
      axgc.text(j, i, data[i, j], ha="center", va="center", color=color)

  axgc.set_title(f"DX Spots From {continent}", fontsize=14, fontweight='bold')
  fig.text(0.01, 0.02, 'SunFluxBot By W6BSD {}'.format(now.strftime('%Y:%m:%d %H:%M')))
  fig.tight_layout()
  fig.savefig(filename, transparent=False, dpi=100)

def main():
  config = Config()

  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s', datefmt='%H:%M:%S',
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO'))
  )
  if len(sys.argv) < 2:
    logging.error("showdxcc [%s]", '|'.join(CONTINENTS))
    sys.exit(os.EX_USAGE)

  continent = sys.argv[1].upper()
  if continent not in CONTINENTS:
    logging.error("showdxcc [%s]", '|'.join(CONTINENTS))
    sys.exit(os.EX_USAGE)

  if len(sys.argv) == 3:
    filename = os.path.join('/tmp', sys.argv[2])
  else:
    tmpdir = config.get('showdxcc.target_dir', '/var/tmp/dxcc')
    target_dir = os.path.join(tmpdir, continent)
    os.makedirs(target_dir, exist_ok=True)
    now = datetime.utcnow().strftime('%Y%m%d%H%M')
    filename = os.path.join(target_dir, f'dxcc-{continent}-{now}.png')

  get_dxcc(config, continent, filename)
  logging.info('Save %s', filename)
  sys.exit(os.EX_OK)

if __name__ == "__main__":
  sys.exit(main())
