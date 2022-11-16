#!/usr/bin/env python3

import logging
import sqlite3

from datetime import datetime
from datetime import timedelta

import adapters

from config import Config

logging.basicConfig(
  format='%(asctime)s %(name)s:%(lineno)d %(levelname)s - %(message)s',
  level=logging.INFO
)

def purge(conn, purge_time):
  logging.info("Purge entries from before: %s", purge_time.isoformat())

  with conn:
    curs = conn.cursor()
    curs.execute('DELETE FROM dxspot WHERE time < ?;', (purge_time,))
    logging.info('%d record deleted', curs.rowcount)

def main():
  adapters.install_adapers()
  config = Config()
  delta = timedelta(hours=config.get('dxcluster.purge_time', 192))
  cnx_timeout = int(config['dxcluster.db_timeout']/3) or 1
  purge_time = datetime.utcnow() - delta

  logging.info('Database: %s, timeout %d', config['dxcluster.db_name'],
               config['dxcluster.db_timeout'])
  conn = sqlite3.connect(
    config['dxcluster.db_name'], timeout=cnx_timeout,
    detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES
  )

  try:
    purge(conn, purge_time)
  except sqlite3.OperationalError as err:
    logging.error(err)

if __name__ == "__main__":
  main()
