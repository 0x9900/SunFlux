#!/usr/bin/env python3

import logging
import os
import sqlite3

from datetime import datetime
from datetime import timedelta

import adapters

from config import Config

logging.basicConfig(
  format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s',
  level=logging.INFO
)

sqlite3.register_adapter(datetime, adapters.adapt_datetime)
sqlite3.register_converter('timestamp', adapters.convert_datetime)

def main():
  config = Config()
  delta = timedelta(hours=config.get('purge.time', 12))
  purge_time = datetime.utcnow() - delta

  conn = sqlite3.connect(
    config['cluster.db_name'], timeout=config['cluster.db_timeout'],
    detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES
  )

  with conn:
    curs = conn.cursor()
    res = curs.execute('select count(*) from dxspot;')
    count1 =  res.fetchone()[0]

  with conn:
    curs = conn.cursor()
    curs.execute('delete from dxspot where time < ?;', (PURGE_TIME,))
    logging.info("Now: %s <=> %s", datetime.utcnow().isoformat(),
                 PURGE_TIME.isoformat())
  with conn:
    curs = conn.cursor()
    res = curs.execute('select count(*) from dxspot;')
    count2 =  res.fetchone()[0]

  logging.info('Count %d before delete', count1)
  logging.info('Count %d after delete', count2)
  logging.info('%d records deleted', count1 - count2)
