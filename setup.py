#!/usr/bin/env python3
#
import sys

from setuptools import setup, find_packages

__author__ = "Fred C. (W6BSD)"
__version__ = '0.1.0'
__license__ = 'BSD'

py_version = sys.version_info[:2]
if py_version < (3, 8):
  raise RuntimeError('SunFlux Bot requires Python 3.8 or later')

setup(
  name='SunFluxBot',
  version=__version__,
  description='SA818 Programming Software',
  long_description='Telegram Fun Flux Bot',
  long_description_content_type='text/markdown',
  url='https://github.com/0x9900/SunFlux',
  license=__license__,
  author=__author__,
  author_email='w6bsd@bsdworld.org',
  py_modules=['config', 'adapters', 'dxcluster', 'fluxgraph',
              'kpindexgraph', 'outlookgraph', 'showdxcc',
              'ssngraph', 'sunfluxbot'],
  install_requires=['numpy', 'matplotlib', 'python-telegram-bot'],
  entry_points = {
    'console_scripts': [
      'dxcluster = dxcluster:main',
      'fluxgraph = fluxgraph:main',
      'kpindexgraph = kpindexgraph:main',
      'outlookgraph = outlookgraph:main',
      'showdxcc = showdxcc:main',
      'ssngraph = ssngraph:main',
      'sunfluxbot = sunflux:main',
    ]
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
