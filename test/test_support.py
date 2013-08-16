#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   test support functions
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

import struct
import os
import array
import sys
import unittest
import random


class RandomSeededTestCase(unittest.TestCase):
    def __init__(self, methodName='runTest', seedVarName='TEST_SEED'):
        unittest.TestCase.__init__(self, methodName=methodName)
        self.seed_var_name = seedVarName
        self.test_name = 'Unnamed test'
        self.trial = 0
        self.trial_count = 0
        #self.prev_trial = 0

    def setUp(self):
        # In sub classes use the following to call this setUp() from an overrided setUp()
        # super(<sub-class>, self).setUp()
        
        # Use seed from enviroment if it is set
        try:
            seed = long(os.environ[self.seed_var_name])
        except KeyError:
            random.seed()
            seed = long(random.random() * 1e9)

        print('\n * Random seed: {} *'.format(seed))
        random.seed(seed)

    def update_progress(self, cur_trial, dotted=True):
        self.trial = cur_trial
        if not dotted:
            print('\r  {} {} / {}  '.format(self.test_name, self.trial, self.trial_count), end='')
        else:
            if self.trial == 1:
                print('  {} '.format(self.test_name), end='')
            print('.', end='')
        #self.prev_trial = self.trial
        sys.stdout.flush()


        
def write_bin_file(fname, samples, sample_period, start_time):
    with open(fname, 'wb') as fo:
        fo.write(struct.pack('<f', sample_period))
        fo.write(struct.pack('<f', start_time))
        for s in samples:
            fo.write(struct.pack('<f', s))
            
def read_bin_file(fname):
    with open(fname, 'rb') as fo:
        sample_period = struct.unpack('<f', fo.read(4))[0]
        start_time = struct.unpack('<f', fo.read(4))[0]

        num_samples = (os.path.getsize(fname) - (2 * 4)) // 4
        samples = array.array('f')
        try:
            samples.fromfile(fo, num_samples)
        except EOFError:
            raise EOFError('Missing samples in file')
            
        # On a big-endian machine the samples need to be byteswapped
        if sys.byteorder == 'big':
            samples.byteswap()
        
        return (samples, sample_period, start_time)

