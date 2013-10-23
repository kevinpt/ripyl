#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   Cython test suite
'''

# Copyright © 2013 Kevin Thibedeau

# This file is part of Ripyl.

# Ripyl is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.

# Ripyl is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with Ripyl. If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function, division

import unittest

import ripyl
import ripyl.config as cfg


class TestCython(unittest.TestCase):
    def test_cython_config(self):
        print('\nConfig settings:')
        print('  Use Cython:', cfg.settings.use_cython)
        print('  Cython prebuild:', cfg.settings.cython_prebuild)
        print('  Python fallback:', cfg.settings.python_fallback)
        print('  Config source:', cfg.settings.config_source)
        print('  Config path:', cfg.settings.config_path)

        print('\nCython patched objects:')
        for po in cfg.settings.patched_objs:
            print('  {}.{}\t{}'.format(po.py_mname, po.obj_name, 'ACTIVE' if po.active else 'inactive'))
