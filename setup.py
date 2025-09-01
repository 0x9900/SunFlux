#!/usr/bin/env python3
#
# BSD 3-Clause License
#
# Copyright (c)2022-2025 Fred W6BSD
# All rights reserved.
#
#

import sys

from setuptools import find_namespace_packages, setup

__author__ = "Fred C. (W6BSD)"
__version__ = '0.1.6'
__license__ = 'BSD'

py_version = sys.version_info[:2]
if py_version < (3, 10):
  raise RuntimeError('SunFlux Bot requires Python 3.10 or later')

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
    'dlayer',
    'eisngraph',
    'fluxgraph',
    'graphmodes',
    'outlookgraph',
    'pkiforecast',
    'pkiwwv',
    'proton_flux',
    'showdxcc',
    'solarwind',
    'ssngraph',
    'ssnhist',
    'tools',
    'xray_flux',
  ],
  # install_requires=['numpy', 'matplotlib'],
  entry_points={
    'console_scripts': [
      'aindex = aindex:main',
      'dlayer = dlayer:main',
      'eisngraph = eisngraph:main',
      'fluxgraph = fluxgraph:main',
      'graphmodes = graphmodes:main',
      'outlookgraph = outlookgraph:main',
      'pkiforecast = pkiforecast:main',
      'pkiwwv = pkiwwv:main',
      'proton_flux = proton_flux:main',
      'showdxcc = showdxcc:main',
      'solarwind = solarwind:main',
      'ssngraph = ssngraph:main',
      'ssnhist = ssnhist:main',
      'xray_flux = xray_flux:main',
    ]
  },
  classifiers=[
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: BSD License',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.10',
    'Topic :: Communications :: Ham Radio',
  ],
)
