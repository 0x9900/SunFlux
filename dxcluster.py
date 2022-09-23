#!/usr/bin/env python3
#
# (c) 2022 Fred C. (W6BSD)
#
# b'DX de SP5NOF:   10136.0  UI5A     FT8 +13dB from KO85 1778Hz   2138Z\r\n'
# b'WWV de W0MU <18Z> :   SFI=93, A=4, K=2, No Storms -> No Storms\r\n'
#
# pylint: disable=no-member,unspecified-encoding

import csv
import io
import logging
import logging.handlers
import os
import random
import re
import socket
import sys
import time

from collections import namedtuple
from copy import copy
from datetime import datetime
from itertools import cycle
from queue import Queue
from telnetlib import Telnet
from threading import Thread

import sqlite3

from importlib.resources import files

import adapters

from config import Config

FIELDS = ['DE', 'FREQUENCY', 'DX', 'MESSAGE', 'DE_CONT', 'TO_CONT',
          'DE_ITUZONE', 'TO_ITUZONE', 'DE_CQZONE', 'TO_CQZONE',
          'BAND', 'DX_TIME']

SQL_TABLE = """
CREATE TABLE IF NOT EXISTS dxspot
(
  de TEXT,
  frequency NUMERIC,
  dx TEXT,
  message TEXT,
  de_cont TEXT,
  to_cont TEXT,
  de_ituzone INTEGER,
  to_ituzone INTEGER,
  de_cqzone INTEGER,
  to_cqzone INTEGER,
  band INTEGER,
  time TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_time on dxspot (time DESC);
CREATE INDEX IF NOT EXISTS idx_de_cont on dxspot (de_cont);
CREATE INDEX IF NOT EXISTS idx_de_cqzone on dxspot (de_cqzone);
CREATE TABLE IF NOT EXISTS wwv
(
  SFI INTEGER,
  A INTEGER,
  K INTEGER,
  conditions TEXT,
  time TIMESTAMP
);
CREATE INDEX IF NOT EXISTS wwv_idx_time on wwv (time DESC);
"""

TELNET_TIMEOUT = 37
DETECT_TYPES = sqlite3.PARSE_DECLTYPES

LOG = logging.root

def create_db(config):
  try:
    conn = sqlite3.connect(config['db_name'], timeout=config['db_timeout'],
                           detect_types=DETECT_TYPES, isolation_level=None)
    LOG.info("Database: %s", config['db_name'])
  except sqlite3.OperationalError as err:
    LOG.error("Database: %s - %s", config['db_name'], err)
    sys.exit(os.EX_IOERR)

  with conn:
    curs = conn.cursor()
    curs.executescript(SQL_TABLE)


class DBInsert(Thread):
  def __init__(self, config, queue):
    super().__init__()
    self.config = config
    self.queue = queue

  def run(self):
    try:
      conn = sqlite3.connect(
        self.config['db_name'], timeout=self.config['db_timeout'],
        detect_types=DETECT_TYPES, isolation_level=None
      )
      LOG.info("Database: %s", self.config['db_name'])
    except sqlite3.OperationalError as err:
      LOG.error("Database: %s - %s", self.config['db_name'], err)
      sys.exit(os.EX_IOERR)

    while True:
      # waiting for something to show up in the queue
      while self.queue.empty():
        time.sleep(0.25)

      while self.queue.qsize():
        request = self.queue.get()
        # Loop as long as the database is unlocked
        while True:
          try:
            curs = conn.cursor()
            curs.execute(*request)
          except sqlite3.OperationalError as err:
            time.sleep(1)
            LOG.warning("Queue len: %d - Error: %s", self.queue.qsize(), err)
          else:
            break

class DXCCRecord:
  __slots__ = ['prefix', 'country', 'ctn', 'continent', 'cqzone',
               'ituzone', 'lat', 'lon', 'tz']

  def __init__(self, *args):
    for idx, field in enumerate(DXCCRecord.__slots__):
      if field == 'prefix':
        prefix, *_ = args[idx].lstrip('*').split('/')
        setattr(self, field, prefix)
      elif field in ('cqzone', 'ituzone'):
        setattr(self, field, int(args[idx]))
      elif field in ('lat', 'lon', 'tz'):
        setattr(self, field, float(args[idx]))
      else:
        setattr(self, field, args[idx])

  def __copy__(self):
    return type(self)(*[getattr(self, f) for f in DXCCRecord.__slots__])

  def __repr__(self):
    buffer = ', '.join([f"{f}: {getattr(self, f)}" for f in DXCCRecord.__slots__])
    return f"<DXCCRecord> {buffer}"


class DXCC:

  __parser = re.compile(r'(?:=|)(?P<prefix>\w+)(?:/\w+|)(?:\((?P<cqzone>\d+)\)|)'
                        r'(?:\[(?P<ituzone>\d+)\]|)(?:{(?P<continent>\w+)}|).*')
  def __init__(self):
    self._map = {}
    cty = files('bigcty').joinpath('cty.csv').read_text()
    LOG.debug('Read bigcty callsign database')
    csvfd = csv.reader(io.StringIO(cty))
    for row in csvfd:
      self._map.update(self.parse(row))
    self.max_len = max(len(v) for v in self._map)

  @staticmethod
  def parse(record):
    dxmap = {}
    cty = DXCCRecord(*record[:9])
    dxmap[cty.prefix] = cty
    extra = record[9]
    for tag in extra.replace(';', '').split():
      match = DXCC.__parser.match(tag)
      if match:
        _cty = copy(cty)
        for key, val in match.groupdict().items():
          if not val:
            continue
          setattr(_cty, key, val)
          dxmap[_cty.prefix] = _cty
      else:
        LOG.error('No match for %s', tag)

    return dxmap

  def lookup(self, call):
    prefixes = {call[:c] for c in range(self.max_len, 0, -1)}
    for prefix in sorted(prefixes, reverse=True):
      if prefix in self._map:
        return self._map[prefix]
    raise KeyError(f"{call} not found")

  def __str__(self):
    return f"{self.__class__} {id(self)} ({len(self._map)} records)"

  def __repr__(self):
    return str(self)


class Record(namedtuple('UserRecord', FIELDS)):
  def __new__(cls, items):
    _items = items
    _items.append(get_band(_items[1]))
    _items.append(datetime.utcnow())
    return tuple.__new__(cls, _items)


def get_band(freq):
  # Quick and dirty way to convert frequencies to bands.
  # I should probably have a band plan for each ITU zones.
  # Sorted by the most popular to the least popular band
  _bands = [
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
    (5260, 5450, 60),
    (420000, 450000, 0.70),
    (219000, 225000, 1.25),
    (1240000, 1300000, 0.23),
    (10000000, 10500000, 0.02),
    (472, 479, 630),
  ]

  for _min, _max, band in _bands:
    if _min <= freq <= _max:
      return band
  LOG.warning("No band for the frequency %s", freq)
  return 0


def login(call, telnet):
  try:
    telnet.expect([b'Please enter your call.*\n'])
  except socket.timeout:
    raise OSError('Connection timeout') from None
  except EOFError as err:
    raise OSError(err) from None
  telnet.write(str.encode(f'{call}\n'))
  telnet.expect([str.encode(f'{call} de .*\n')])
  # telnet.write(b'Set Dx Filter SpotterCont=NA\n')
  telnet.write(b'Set Dx Filter\n')
  telnet.expect(['DX filter.*\n'.encode()])


def parse_spot(line):
  #
  # DX de DO4DXA-#:  14025.0  GB22GE       CW 10 dB 25 WPM CQ             1516Z
  # 0.........1.........2.........3.........4.........5.........6.........7.........8
  #           0         0         0         0         0         0         0         0
  if not hasattr(parse_spot, 'dxcc'):
    parse_spot.dxcc = DXCC()

  if not hasattr(parse_spot, 'splitter'):
    parse_spot.splitter = re.compile(r'[:\s]+').split

  line = line.decode('UTF-8').rstrip()
  elem = parse_spot.splitter(line)[2:]

  try:
    fields = [
      elem[0].strip('-#'),
      float(elem[1]),
      elem[2],
      ' '.join(elem[3:len(elem) - 1]),
    ]
  except ValueError as err:
    LOG.warning("%s | %s", err, line)
    return None

  for c_code in fields[0].split('/', 1):
    try:
      call_de = parse_spot.dxcc.lookup(c_code)
      break
    except KeyError:
      pass
  else:
    LOG.warning("%s Not found | %s", fields[0], line)
    return None

  for c_code  in fields[2].split('/', 1):
    try:
      call_to = parse_spot.dxcc.lookup(c_code)
      break
    except KeyError:
      pass
  else:
    LOG.warning("%s Not found | %s", fields[2], line)
    return None

  fields.extend([
    call_de.continent,
    call_to.continent,
    call_de.ituzone,
    call_to.ituzone,
    call_de.cqzone,
    call_to.cqzone,
  ])
  return Record(fields)


def parse_wwv(line):
  if not hasattr(parse_wwv, 'decoder'):
    parse_wwv.decoder = re.compile(
      r'.*\<(?P<Z>\d+)Z\>.*\sSFI=(?P<SFI>\d+), A=(?P<A>\d+), K=(?P<K>\d+), (?P<conditions>.*)$'
    )

  line = line.decode('UTF-8')
  _fields = parse_wwv.decoder.match(line.rstrip())
  if not _fields:
    return None

  fields = {}
  for key, val in _fields.groupdict().items():
    fields[key] = val if key == 'conditions' else int(val)
  fields['time'] = datetime.utcnow()
  return fields


def read_stream(queue, telnet):
  expect_exp = [b'DX.*\n', b'WWV de .*\n']
  current = time.time()
  while True:
    code, _, buffer = telnet.expect(expect_exp, timeout=TELNET_TIMEOUT)
    if code == 0:
      current = time.time()
      rec = parse_spot(buffer)
      if not rec:
        continue
      queue.put(["INSERT INTO dxspot VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
        rec.DE, rec.FREQUENCY, rec.DX, rec.MESSAGE, rec.DE_CONT, rec.TO_CONT,
        rec.DE_ITUZONE, rec.TO_ITUZONE, rec.DE_CQZONE, rec.TO_CQZONE, rec.BAND,
        rec.DX_TIME)])
    elif code == 1:
      fields = parse_wwv(buffer)
      LOG.info("WWV Fields %s", repr(fields))
      if not fields:
        continue
      queue.put(["INSERT INTO wwv VALUES (?,?,?,?,?)", (
        fields['SFI'], fields['A'], fields['K'], fields['conditions'],
        fields['time'])])
    elif code == -1:            # timeout
      if current < time.time() - 120:
        break
      LOG.warning('Timeout - sleeping for a few seconds [%s]', telnet.host)
      time.sleep(5)


def main():
  global LOG                    # pylint: disable=global-statement

  adapters.install_adapers()

  _config = Config()
  config = _config.get('dxcluster')
  del _config

  logging.basicConfig(
    format='%(asctime)s %(name)s[%(thread)s]:%(lineno)d %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
  )
  LOG = logging.getLogger('dxcluster')
  loglevel = os.getenv('LOGLEVEL', config.get('log_level', 'INFO'))
  if loglevel not in logging._nameToLevel: # pylint: disable=protected-access
    LOG.error('Log level "%s" does not exist, defaulting to INFO', loglevel)
    loglevel = logging.INFO
  LOG.setLevel(loglevel)

  clusters = []
  for server in config['servers']:
    host, port = server.split(':')
    clusters.append((host, int(port)))

  create_db(config)

  queue = Queue()
  db_thread = DBInsert(config, queue)
  db_thread.setDaemon(True)
  db_thread.start()

  random.shuffle(clusters)
  for cluster in cycle(clusters):
    try:
      telnet = Telnet(*cluster, timeout=300)
      LOG.info("Connection to %s:%d open", telnet.host, telnet.port)
      login(config['call'], telnet)
      LOG.info("%s identified", config['call'])
      read_stream(queue, telnet)
    except OSError as err:
      LOG.error("%s - %s - Sleeping 10 seconds before retrying", err, cluster)
      time.sleep(10)

if __name__ == "__main__":
  main()
