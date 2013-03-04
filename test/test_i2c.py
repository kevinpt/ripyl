#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Protocol decode library
   i2c.py test suite
'''

# Copyright © 2013 Kevin Thibedeau

# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:

# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
from __future__ import print_function, division

import unittest
import random

import ripyl.protocol.i2c as i2c
import ripyl.sigproc as sigp
import ripyl.streaming as streaming

class TestI2CFuncs(unittest.TestCase):
    def test_i2c_decode(self):
        print('')
        trials = 20
        for i in xrange(trials):
            print('\r  I2C transfer {0} / {1}  '.format(i+1, trials), end='')
    
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
                #r_wn = 1
                
                # reads with 10-bit addressing are special
                if r_wn == i2c.I2C.Read and addr > 0x77:
                    transfers.append(i2c.I2CTransfer(i2c.I2C.Write, addr, data))
                    transfers.append(i2c.I2CTransfer(r_wn, addr, data))
                else:
                    transfers.append(i2c.I2CTransfer(r_wn, addr, data))
            
            use_edges = random.choice((True, False))                
            
            scl, sda = zip(*list(i2c.i2c_synth(transfers, clock_freq, idle_start=3.0e-5, idle_end=3.0e-5)))
            scl = sigp.remove_excess_edges(iter(scl))
            sda = sigp.remove_excess_edges(iter(sda))

            if use_edges:
                records_it = i2c.i2c_decode(scl, sda, stream_type=streaming.StreamType.Edges)
            else:
                sample_period = 1.0 / (20.0 * clock_freq)
                scl_s = sigp.sample_edge_list(scl, sample_period)
                sda_s = sigp.sample_edge_list(sda, sample_period)
                
                records_it = i2c.i2c_decode(scl_s, sda_s, stream_type=streaming.StreamType.Samples)
                
            records = list(records_it)
            
            #print('Decoded:', [str(r) for r in records])
            
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
                
