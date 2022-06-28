#!/usr/bin/env python3
#
# (c) 2022 Fred C. (W6BSD)
#
# b'DX de SP5NOF:   10136.0  UI5A     FT8 +13dB from KO85 1778Hz   2138Z\r\n'

import csv
import logging
import logging.handlers
import os
import random
import re
import socket
import time

from collections import namedtuple
from datetime import datetime
from itertools import cycle
from telnetlib import Telnet

import sqlite3

import adapters

from config import Config

# Sorted by the most popular to the least popular band
BANDS = [
  (14000, 14350, 20),
  (7000, 7300, 40),
  (10100, 10150, 30),
  (3500, 4000, 80),
  (21000, 21450, 15),
  (18068, 18168, 17),
  (28000, 29700, 10),
  (50000, 54000, 6),
  (24890, 24990, 12),
  (1800, 2000, 160),
  (144000, 148000, 2),
  (69900, 70500, 4),
  (5330, 5410, 60),
  (420000, 450000, 0.70),
  (219000, 225000, 1.25),
  (472, 479, 630),
]

FIELDS = ['DE', 'FREQUENCY', 'DX', 'MESSAGE', 'CONT_DE', 'CONT_DX',
          'BAND', 'DX_TIME']

SQL_TABLE = """
CREATE TABLE IF NOT EXISTS dxspot
(
  de TEXT,
  frequency NUMERIC,
  dx TEXT,
  message TEXT,
  cont_de TEXT,
  cont_dx TEXT,
  band INTEGER,
  time TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_time on dxspot (time DESC);
CREATE INDEX IF NOT EXISTS idx_cont_dx on dxspot (cont_dx);
"""

sqlite3.register_adapter(datetime, adapters.adapt_datetime)
sqlite3.register_converter('timestamp', adapters.convert_datetime)

LOG = logging.getLogger(__name__)

class DXCC:

  __parsers = (
    re.compile(r'^(?:=|)(\w+).*$'),
  )

  def __init__(self, filename=None):
    self._map = {}
    if not filename:
      filename = 'bigcty/cty.csv'
    with open(filename, 'r', encoding='utf-8') as csvfile:
      csvfd = csv.reader(csvfile)
      for row in csvfd:
        self._map[row[0].strip('*')] = row[3]
        for prefix in DXCC.parse(row[9]):
          self._map[prefix] = row[3]
    self.max_len = max([len(v) for v in self._map])

  @staticmethod
  def parse(line):
    line = line.strip(';').split()
    prefixes = []
    for parser in DXCC.__parsers:
      for pre in line:
        match = parser.match(pre)
        if match:
          prefixes.append(match.group(1))
    return prefixes

  def lookup(self, call):
    if call in self._map:
      return self._map[call]

    prefixes = {call[:c] for c in range(self.max_len, 0, -1)}
    for prefix in sorted(prefixes, reverse=True):
      if prefix in self._map:
        return self._map[prefix]
    LOG.warning('DXCC lookup error for "%s"', call)
    return ''

class Record(namedtuple('UserRecord', FIELDS)):
  def __new__(cls, items):
    _items = [x.strip() for x in items]
    _items[1] = float(_items[1])
    _items.append(get_band(_items[1]))
    _items.append(datetime.utcnow())
    return tuple.__new__(cls, _items)

def get_band(freq):
  # Quick and dirty way to convert frequencies to bands.
  # I should probably have a band plan for each ITU zones.
  for _min, _max, band in BANDS:
    if _min <= freq <= _max:
      return band
  LOG.warning("No band for the frequency %s", freq)
  return 0

def login(call, cnx):
  try:
    match = cnx.expect([b'Please enter your call.*\n'])
  except socket.timeout:
    raise OSError('Connection timeout') from None
  except EOFError as err:
    raise OSError(err) from None
  cnx.write(str.encode(f'{call}\n'))
  match = cnx.expect([str.encode(f'{call} de .*\n')])
  print(match[2].decode('ASCII'))
  # cnx.write(b'Set Dx Filter SpotterCont=NA\n')
  cnx.write(b'Set Dx Filter\n')
  match = cnx.expect(['DX filter.*\n'.encode()])
  print(match[2].decode('ASCII'))

def read_stream(cdb, cnx):
  dxcc = DXCC()
  regex = re.compile(
    r'^DX de\s(\w+)(?:.*):\s+(\d+.\d+)\s+(\w+)(?:|\S+)\s+(.*)(?:\d{4}Z).*'
  )
  while True:
    code, _, buffer = cnx.expect([b'DX.*\n', b'WWV de .*\n'], timeout=10)
    if code == 0:         # timeout
      buffer = buffer.decode('UTF-8')
      match = regex.match(buffer)
      if not match:
        LOG.error("Error: %s", buffer)
        continue

      fields = list(match.groups())
      fields.append(dxcc.lookup(fields[0]))
      fields.append(dxcc.lookup(fields[2]))
      try:
        rec = Record(fields)
      except ValueError as err:
        LOG.error("%s - %s", err, repr(fields))
        continue
      LOG.debug(rec)
      try:
        with cdb:
          curs = cdb.cursor()
          curs.execute("INSERT INTO dxspot VALUES (?,?,?,?,?,?,?,?)", (
            rec.DE, rec.FREQUENCY, rec.DX, rec.MESSAGE,
            rec.CONT_DE, rec.CONT_DX, rec.BAND, rec.DX_TIME,
          ))
      except sqlite3.OperationalError as err:
        logging.error(err)
    elif code == 1:
      buffer = buffer.decode('UTF-8')
      LOG.info(buffer)
    elif code == -1:
      LOG.warning('Timeout - sleeping for a few seconds [%s]', cnx.host)
      return

def main():
  config = Config()

  formatter = logging.Formatter("%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s")
  file_handler = logging.FileHandler(config['cluster.log_file'], 'a')
  file_handler.setLevel(logging.DEBUG)
  file_handler.setFormatter(formatter)

  console_handler = logging.StreamHandler()
  console_handler.setLevel(logging.INFO)
  console_handler.setFormatter(formatter)

  loglevel = logging.getLevelName(os.getenv('LOGLEVEL', 'INFO'))
  if loglevel not in logging._levelToName: # pylint: disable=protected-access
    loglevel = logging.INFO
  LOG.setLevel(loglevel)
  LOG.addHandler(file_handler)
  LOG.addHandler(console_handler)

  con = sqlite3.connect(
    config['cluster.db_name'],
    timeout=config['cluster.db_timeout'],
    detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES
  )
  clusters = []
  for server in config['cluster.servers']:
    clusters.append(server.split(':'))

  with con:
    curs = con.cursor()
    curs.executescript(SQL_TABLE)

  random.shuffle(clusters)
  for cluster in cycle(clusters):
    try:
      telnet = Telnet(*cluster, timeout=300)
      LOG.info("Connection to %s open", telnet.host)
      login(config['cluster.call'], telnet)
      LOG.info("%s identified", config['cluster.call'])
      read_stream(con, telnet)
    except OSError as err:
      LOG.error(err)
    time.sleep(30)


if __name__ == "__main__":
  main()
