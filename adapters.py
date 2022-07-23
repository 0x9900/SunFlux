#
"""Save datetime object as timestamp in SQLite"""

import sqlite3

from datetime import datetime

def adapt_datetime(t_stamp):
  return t_stamp.timestamp()

def convert_datetime(t_stamp):
  try:
    return datetime.fromtimestamp(float(t_stamp))
  except ValueError:
    return None

sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter('timestamp', convert_datetime)
