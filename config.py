#
# BSD 3-Clause License
#
# Copyright (c) 2021, Fred W6BSD
# All rights reserved.
#
#

import os
import yaml
import logging
import sys

CONFIG_FILENAME = "sunflux.yaml"
CONFIG_LOCATIONS = ['/etc', '~/.local', '.']

class Config:
  _instance = None
  config_data = None
  def __new__(cls, *args, **kwargs):
    if cls._instance is None:
      cls._instance = super(Config, cls).__new__(cls)
      cls._instance.config_data = {}
    return cls._instance

  def __init__(self):
    self.log = logging.getLogger('Config')
    if self.config_data:
      return

    for path in CONFIG_LOCATIONS:
      filename = os.path.expanduser(os.path.join(path, CONFIG_FILENAME))
      if os.path.exists(filename):
        self.log.debug('Reading config file: %s', filename)
        try:
          self.config_data = self._read_config(filename)
        except ValueError as err:
          self.log.error('Configuration error "%s"', err)
          sys.exit(os.EX_CONFIG)
        return
    self.log.error(f'Configuration file "{CONFIG_FILENAME}" not found')
    sys.exit(os.EX_CONFIG)

  def to_yaml(self):
    return yaml.dump(self.config_data)

  def get(self, key, default=None):
    try:
      return self[key]
    except KeyError:
      return default

  def __getitem__(self, attr):
    section, attribute = attr.split('.')
    if section not in self.config_data:
      raise KeyError("'{}' object has no section '{}'".format(self.__class__, section))
    config = self.config_data[section]
    if attribute not in config:
      raise KeyError("'{}' object has no attribute '{}'".format(self.__class__, attr))
    return config[attribute]

  @staticmethod
  def _read_config(filename):
    with open(filename, 'r') as confd:
      configuration = yaml.safe_load(confd)
    return configuration
