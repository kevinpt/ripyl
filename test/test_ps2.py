#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   ps2.py test suite
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

import ripyl.protocol.ps2 as ps2
import ripyl.sigproc as sigp
import ripyl.streaming as streaming
import test.test_support as tsup

class TestPS2Funcs(tsup.RandomSeededTestCase):

    def test_ps2_decode(self):
        self.test_name = 'PS/2 message'
        self.trial_count = 20
        for i in xrange(self.trial_count):
            self.update_progress(i+1)
            
            clock_freq = random.uniform(10.0e3, 13.0e3)
            
            frames = []
            for _ in xrange(random.randint(4, 20)):
                frames.append(ps2.PS2Frame(random.randint(0, 2**8-1), \
                    random.choice((ps2.PS2Dir.DeviceToHost, ps2.PS2Dir.HostToDevice))) \
                )
                
            use_edges = random.choice((True, False))
                            
            clk, data = ps2.ps2_synth(frames, clock_freq, 4.0 / clock_freq, 5.0 / clock_freq)

            if use_edges:
                records_it = ps2.ps2_decode(clk, data, stream_type=streaming.StreamType.Edges)
                
            else: # samples
                #sr = 1.0e-2
                sample_period = 1.0 / (20.0 * clock_freq)
                #sample_period = 10.0e-2
                clk_s = sigp.edges_to_sample_stream(clk, sample_period)
                data_s = sigp.noisify(sigp.edges_to_sample_stream(data, sample_period))

                records_it = ps2.ps2_decode(clk_s, data_s)
                            
            records = list(records_it)
            #print('\nDecoded:', [str(r) for r in records])
            #print(records[-1].start_time, records[-1].end_time)
            
            msg_ix = 0
            match = True
            frame_cnt = 0
            for r in records:
                if r.kind == 'PS/2 frame':
                    frame_cnt += 1
                    #print('Data:', r.data, msg[msg_ix])
                    if r.data != frames[msg_ix]:
                        match = False
                        break
                    msg_ix += 1
                    
            self.assertTrue(match, msg='Message not decoded successfully')
            self.assertEqual(frame_cnt, len(frames), 'Missing or extra decoded messages')
                
