#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   spi.py test suite
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

import ripyl.protocol.spi as spi
import ripyl.sigproc as sigp
import ripyl.streaming as streaming

class TestSPIFuncs(unittest.TestCase):
    def test_spi_decode(self):
        print('')
        trials = 20
        for i in xrange(trials):
            print('\r  SPI message {0} / {1}  '.format(i+1, trials), end='')
            
            cpol = random.choice((0, 1))
            cpha = random.choice((0, 1))
            lsb_first = random.choice((True, False))
            
            word_size = random.randint(8, 32)
            clock_freq = random.uniform(1.0e3, 1.0e7)
            
            msg = []
            for _ in xrange(random.randint(4, 20)):
                msg.append(random.randint(0, 2**word_size-1))
                
            use_edges = random.choice((True, False))                
                
            # msg = [3, 4, 5, 240]
            # word_size = 8
            # clock_freq = 30.0
            # lsb_first = True
            # cpol = 0
            # cpha = 1
            # use_edges = False
            
            clk, mosi, cs = zip(*list(spi.spi_synth(msg, word_size, clock_freq, cpol, cpha, lsb_first, 4.0 / clock_freq, 0.0)))
            
            clk = sigp.remove_excess_edges(iter(clk))
            mosi = sigp.remove_excess_edges(iter(mosi))
            cs = sigp.remove_excess_edges(iter(cs))
            
            if use_edges:
                records_it = spi.spi_decode(clk, mosi, cs, cpol=cpol, cpha=cpha, lsb_first=lsb_first, stream_type=streaming.StreamType.Edges)
                
            else: # samples
                #sr = 1.0e-2
                sample_period = 1.0 / (20.0 * clock_freq)
                #sample_period = 10.0e-2
                clk_s = sigp.edges_to_sample_stream(clk, sample_period)
                mosi_s = sigp.noisify(sigp.edges_to_sample_stream(mosi, sample_period))
                cs_s = sigp.noisify(sigp.edges_to_sample_stream(cs, sample_period))

                records_it = spi.spi_decode(clk_s, mosi_s, cs_s, cpol=cpol, cpha=cpha, lsb_first=lsb_first)
                            
            records = list(records_it)
            #print('\nDecoded:', [str(r) for r in records])
            #print(records[-1].start_time, records[-1].end_time)
            
            msg_ix = 0
            match = True
            frame_cnt = 0
            for r in records:
                if r.kind == 'SPI frame':
                    frame_cnt += 1
                    #print('Data:', r.data, msg[msg_ix])
                    if r.data != msg[msg_ix]:
                        match = False
                        break
                    msg_ix += 1
                    
            self.assertTrue(match, msg='Message not decoded successfully')
            self.assertEqual(frame_cnt, len(msg), 'Missing or extra decoded messages')
                
