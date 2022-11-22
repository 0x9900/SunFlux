#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c) 2022 Fred W6BSD
# All rights reserved.
#
#

import sys

from setuptools import setup, find_namespace_packages

__author__ = "Fred C. (W6BSD)"
__version__ = '0.1.2'
__license__ = 'BSD'

py_version = sys.version_info[:2]
if py_version < (3, 9):
  raise RuntimeError('SunFlux Bot requires Python 3.9 or later')

setup(
  name='SunFluxBot',
  version=__version__,
  description='SunFluxBot',
  long_description='Bot to access Sun activity information',
  long_description_content_type='text/markdown',
  url='https://github.com/0x9900/SunFlux',
  license=__license__,
  author=__author__,
  author_email='w6bsd@bsdworld.org',
  packages=find_namespace_packages(
    where=".",
    exclude=["build*", "misc*", "dist*"]
  ),
  py_modules=[
    'adapters',
    'aindex',
    'config',
    'dxcluster',
    'eisngraph',
    'fluxgraph',
    'kpiforecast',
    'kpiwwv',
    'outlookgraph',
    'purge_cluster',
    'showdxcc',
    'ssngraph',
    'sunfluxbot',
  ],
  install_requires=['numpy', 'matplotlib', 'python-telegram-bot'],
  entry_points = {
    'console_scripts': [
      'aindex = aindex:main',
      'dxcluster = dxcluster:main',
      'eisngraph = eisngraph:main',
      'fluxgraph = fluxgraph:main',
      'kpiforecast = kpiforecast:main',
      'kpiwwv = kpiwwv:main',
      'outlookgraph = outlookgraph:main',
      'purge_cluster = purge_cluster:main',
      'showdxcc = showdxcc:main',
      'ssngraph = ssngraph:main',
      'sunfluxbot = sunfluxbot:main',
    ]
  },
  package_data={
    "bigcty": ["*.csv"],
  },
  classifiers=[
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: BSD License',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.8',
    'Topic :: Communications :: Ham Radio',
  ],
)
