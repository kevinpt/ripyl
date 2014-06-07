#!/usr/bin/python

'''Ripyl protocol decode library'''


__version__ = '1.2.1'

import ripyl.sigproc
import ripyl.decode
import ripyl.streaming
import ripyl.util
import ripyl.protocol
import ripyl.config

# Test if cython is available
try:
    import Cython
    cython_exists = True
except ImportError:
    cython_exists = False


if ripyl.config.settings.use_cython and cython_exists:
    import ripyl.cython
