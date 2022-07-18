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

def purge(conn, purge_time):
  with conn:
    res = conn.execute('select count(*) from dxspot;')
    cnt_before =  res.fetchone()[0]
    # Delete old records
    conn.execute('delete from dxspot where time < ?;', (purge_time,))
    res = conn.execute('select count(*) from dxspot;')
    cnt_after =  res.fetchone()[0]

  logging.info("Purge from: %s to: %s", purge_time.isoformat(), datetime.utcnow().isoformat())
  logging.info('Count %d before delete', cnt_before)
  logging.info('Count %d after delete', cnt_after)
  logging.info('%d records deleted', cnt_before - cnt_after)

def main():
  config = Config()
  delta = timedelta(hours=config.get('dxcluster.purge_time', 12))
  purge_time = datetime.utcnow() - delta

  logging.info('Database: %s, timeout %d', config['dxcluster.db_name'],
               config['dxcluster.db_timeout'])
  conn = sqlite3.connect(
    config['dxcluster.db_name'], timeout=config['dxcluster.db_timeout'],
    detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES
  )

  for retry in range(1, 5):            # number of retries.
    try:
      logging.info('Attempt %d', retry)
      purge(conn, purge_time)
    except sqlite3.OperationalError:
      pass
    else:
      break

if __name__ == "__main__":
  main()
