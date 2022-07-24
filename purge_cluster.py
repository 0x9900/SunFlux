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
  logging.info("Purge entries from before: %s", purge_time.isoformat())

  with conn:
    curs = conn.cursor()
    curs.execute('DELETE FROM dxspot WHERE time < ?;', (purge_time,))
    logging.info('%d record deleted', curs.rowcount)

def main():
  config = Config()
  delta = timedelta(hours=config.get('dxcluster.purge_time', 12))
  cnx_timeout = int(config['dxcluster.db_timeout']/3) or 1
  purge_time = datetime.utcnow() - delta

  logging.info('Database: %s, timeout %d', config['dxcluster.db_name'],
               config['dxcluster.db_timeout'])
  conn = sqlite3.connect(
    config['dxcluster.db_name'], timeout=cnx_timeout,
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
