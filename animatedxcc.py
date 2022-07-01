#!/usr/bin/env python3

import json
import logging
import os
import re
import sys

from subprocess import Popen, PIPE

from urllib.request import urlretrieve
from datetime import datetime, timedelta

from PIL import Image
try:
  from tqdm import tqdm
except ImportError:
  tqdm = iter

#TARGET_DIR = '/Volumes/WDPassport/tmp/dxcc'
TARGET_DIR = '/var/www/html'
CONVERTER = os.path.join(os.getcwd(), 'convert.sh')

logging.basicConfig(level=logging.INFO)

def animate(continent):
  animation = os.path.join(TARGET_DIR, f'dxcc-{continent}.gif')
  image_list = []

  file_list = sorted(os.listdir(TARGET_DIR))
  for name in tqdm(file_list):
    if not name.startswith(f'dxcc-{continent}-'):
      continue

    fullname = os.path.join(TARGET_DIR, name)
    logging.debug('Add %s', name)
    image = Image.open(fullname)
    image = image.convert('RGB')
    image = image.resize((1290, 700))
    image_list.append(image)

  if len(image_list) > 2:
    logging.info('Saving animation into %s [%d] images', animation, len(image_list))
    image_list[0].save(animation, save_all=True, optimize=True, duration=75,
                       loop=0, append_images=image_list[1:])
  else:
    logging.info('Nothing to animate')

def gen_video(continent):
  logfile = '/tmp/animatedxcc.log'
  gif_file = os.path.join(TARGET_DIR, f'dxcc-{continent}.gif')
  video_file = os.path.join(TARGET_DIR, f'dxcc-{continent}.mp4')
  cmd = f'{CONVERTER} {gif_file} {video_file}'

  with open(logfile, "w") as err:
    print(cmd, file=err)
    proc = Popen(cmd.split(), shell=False, stdout=PIPE, stderr=err)
  logging.info(f"Saving %s video file", video_file)
  proc.wait()
  if proc.returncode != 0:
    logging.error('Error generating the video file')

def main():
  for continent in ('EU', 'NA'): #('AF', 'AS', 'EU', 'NA', 'OC', 'SA'):
    animate(continent)
    gen_video(continent)


if __name__ == "__main__":
  main()
