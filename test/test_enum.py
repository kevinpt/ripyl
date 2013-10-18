#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   Enumeration class test suite
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

from __future__ import print_function

import unittest
import ripyl.util.enum as enum
    
class TestOnlineStats(unittest.TestCase):
    def test_basic(self):
        class TEnum(enum.Enum):
            Item1 = 1
            Item2 = 2
            Item3 = 3

        for i in xrange(1,4):
            value = getattr(TEnum, 'Item' + str(i))
            self.assertEqual(value, i, msg='Enumeration value mismatch')

        for i in xrange(1,4):
            name = TEnum(i)
            self.assertEqual(name, 'Item' + str(i), msg='Short name mismatch: {}'.format(name))

        for i in xrange(1,4):
            name = TEnum(i, full_name=True)
            self.assertEqual(name, 'TEnum.Item' + str(i), msg='Full name mismatch: {}'.format(name))


