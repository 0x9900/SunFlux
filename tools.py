#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c)2023 Fred W6BSD
# All rights reserved.
#
#

from datetime import datetime, timezone

import numpy as np


def remove_outliers(points, low=25, high=95):
  percent_lo = np.percentile(points, low, interpolation='midpoint')
  percent_hi = np.percentile(points, high, interpolation='midpoint')
  iqr = percent_hi - percent_lo
  lower_bound = points <= (percent_lo - 5 * iqr)
  upper_bound = points >= (percent_hi + 5 * iqr)
  points[lower_bound | upper_bound] = np.nan
  return points


def noaa_date(field):
  """Convert the noaa date into a datetime object and make sure the timezone is utc"""
  _date = datetime.strptime(field, '%Y-%m-%dT%H:%M:%S%z')
  _date = _date.replace(tzinfo=timezone.utc)
  return _date


def noaa_date_hook(dct):
  date = noaa_date(dct['time_tag'])
  dct['time_tag'] = date
  return dct
