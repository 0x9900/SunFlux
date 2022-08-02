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
import time

from collections import namedtuple
from copy import copy
from datetime import datetime
from itertools import cycle
from telnetlib import Telnet

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

sqlite3.register_adapter(datetime, adapters.adapt_datetime)
sqlite3.register_converter('timestamp', adapters.convert_datetime)

LOG = logging.getLogger(__name__)

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
    self.max_len = max([len(v) for v in self._map])

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
    (5275, 5450, 60),
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


def login(call, cnx):
  try:
    cnx.expect([b'Please enter your call.*\n'])
  except socket.timeout:
    raise OSError('Connection timeout') from None
  except EOFError as err:
    raise OSError(err) from None
  cnx.write(str.encode(f'{call}\n'))
  cnx.expect([str.encode(f'{call} de .*\n')])
  # cnx.write(b'Set Dx Filter SpotterCont=NA\n')
  cnx.write(b'Set Dx Filter\n')
  cnx.expect(['DX filter.*\n'.encode()])


def parse_spot(line):
  #
  # DX de DO4DXA-#:  14025.0  GB22GE       CW 10 dB 25 WPM CQ             1516Z
  # 0.........1.........2.........3.........4.........5.........6.........7.........8
  #           0         0         0         0         0         0         0         0
  if not hasattr(parse_spot, 'dxcc'):
    parse_spot.dxcc = DXCC()

  line = line.decode('UTF-8')
  pos = line.index(':')
  try:
    fields = [
      line[6:pos].replace('-#','').strip(),
      float(line[pos+1:26].lstrip()),
      line[26:39].rstrip(),
      line[39:70].rstrip(),
    ]
    call_de = parse_spot.dxcc.lookup(fields[0])
    call_to = parse_spot.dxcc.lookup(fields[2])
    fields.extend([
      call_de.continent,
      call_to.continent,
      call_de.ituzone,
      call_to.ituzone,
      call_de.cqzone,
      call_to.cqzone,
    ])
  except (KeyError, ValueError) as err:
    LOG.warning("%s | %s", err, line.rstrip())
    return None
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


def read_stream(cdb, cnx):
  expect_exp = [b'DX.*\n', b'WWV de .*\n']
  current = time.time()
  while True:
    code, _, buffer = cnx.expect(expect_exp, timeout=TELNET_TIMEOUT)
    if code == 0:
      current = time.time()
      rec = parse_spot(buffer)
      if not rec:
        continue
      LOG.debug(rec)
      try:
        with cdb:
          curs = cdb.cursor()
          curs.execute("INSERT INTO dxspot VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            rec.DE, rec.FREQUENCY, rec.DX, rec.MESSAGE,
            rec.DE_CONT, rec.TO_CONT, rec.DE_ITUZONE, rec.TO_ITUZONE,
            rec.DE_CQZONE, rec.TO_CQZONE, rec.BAND, rec.DX_TIME,
          ))
      except sqlite3.OperationalError as err:
        LOG.error(err)
    elif code == 1:
      fields = parse_wwv(buffer)
      LOG.info("WWV Fields %s", repr(fields))
      if not fields:
        continue
      try:
        with cdb:
          curs = cdb.cursor()
          curs.execute("INSERT INTO wwv VALUES (?,?,?,?,?)", (
            fields['SFI'], fields['A'], fields['K'], fields['conditions'],
            fields['time']
          ))
      except sqlite3.OperationalError as err:
        LOG.error(err)
    elif code == -1:            # timeout
      if current < time.time() - 120:
        break
      LOG.warning('Timeout - sleeping for a few seconds [%s]', cnx.host)
      time.sleep(5)


def main():
  global LOG                    # pylint: disable=global-statement

  _config = Config()
  config = _config.get('dxcluster')

  logging.basicConfig(
    format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
  )
  LOG = logging.getLogger(__name__)

  loglevel = os.getenv('LOGLEVEL', config.get('log_level', 'INFO'))
  if loglevel not in logging._nameToLevel: # pylint: disable=protected-access
    LOG.error('Log level "%s" does not exist, defaulting to INFO', loglevel)
    loglevel = logging.INFO
  LOG.setLevel(loglevel)

  clusters = []
  for server in config['servers']:
    clusters.append(server.split(':'))

  try:
    conn = sqlite3.connect(
      config['db_name'],
      timeout=config['db_timeout'],
      detect_types=DETECT_TYPES,
    isolation_level=None
    )
  except sqlite3.OperationalError as err:
    LOG.error("Database: %s - %s", config['db_name'], err)
    return

  with conn:
    curs = conn.cursor()
    curs.executescript(SQL_TABLE)

  random.shuffle(clusters)
  for cluster in cycle(clusters):
    try:
      telnet = Telnet(*cluster, timeout=300)
      LOG.info("Connection to %s open", telnet.host)
      login(config['call'], telnet)
      LOG.info("%s identified", config['call'])
      read_stream(conn, telnet)
    except OSError as err:
      LOG.error(err)

if __name__ == "__main__":
  main()
