#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   i2c.py test suite
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
import random
import sys

import ripyl.protocol.i2c as i2c
import ripyl.sigproc as sigp
import ripyl.streaming as streaming

class TestI2CFuncs(unittest.TestCase):
    def setUp(self):
        import os
        
        # Use seed from enviroment if it is set
        try:
            seed = long(os.environ['TEST_SEED'])
        except KeyError:
            random.seed()
            seed = long(random.random() * 1e9)

        print('\n * Random seed: {} *'.format(seed))
        random.seed(seed)

    def test_i2c_decode(self):
        trials = 20
        for i in xrange(trials):
            print('\r  I2C transfer {0} / {1}  '.format(i+1, trials), end='')
            sys.stdout.flush()
    
            clock_freq = 100.0e3

            transfers = []
            transfers.append(i2c.I2CTransfer(i2c.I2C.Write, 0x23, [1,2,3, 4]))
            transfers.append(i2c.I2CTransfer(i2c.I2C.Write, 0x183, [5, 6, 240]))
            
            transfers = []
            for _ in xrange(random.randint(1, 6)):
                addr = random.randint(1, 2**10-1)
                data = []
                for __ in xrange(random.randint(1, 10)):
                    data.append(random.randint(0, 255))
                    
                r_wn = random.choice((i2c.I2C.Write, i2c.I2C.Read))
                
                # reads with 10-bit addressing are special
                if r_wn == i2c.I2C.Read and addr > 0x77:
                    transfers.append(i2c.I2CTransfer(i2c.I2C.Write, addr, data))
                    transfers.append(i2c.I2CTransfer(r_wn, addr, data))
                else:
                    transfers.append(i2c.I2CTransfer(r_wn, addr, data))
            
            use_edges = random.choice((True, False))                
            
            scl, sda = i2c.i2c_synth(transfers, clock_freq, idle_start=3.0e-5, idle_end=3.0e-5)

            if use_edges:
                records_it = i2c.i2c_decode(scl, sda, stream_type=streaming.StreamType.Edges)
            else:
                sample_period = 1.0 / (20.0 * clock_freq)
                scl_s = sigp.edges_to_sample_stream(scl, sample_period)
                sda_s = sigp.edges_to_sample_stream(sda, sample_period)
                
                records_it = i2c.i2c_decode(scl_s, sda_s, stream_type=streaming.StreamType.Samples)
                
            records = list(records_it)
            
            
            d_txfers = list(i2c.reconstruct_i2c_transfers(iter(records)))
            
            # validate the decoded transfers
            match = True
            for i, t in enumerate(d_txfers):
                if t != transfers[i]:
                    print('\nMismatch:')
                    print('  ', t)
                    print('  ', transfers[i])
                    
                    match = False
                    break
                    
            self.assertTrue(match, msg='Transfers not decoded successfully')
            self.assertEqual(len(d_txfers), len(transfers), 'Missing or extra decoded transfers')
                
