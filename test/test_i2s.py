#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   i2s.py test suite
'''

# Copyright © 2014 Kevin Thibedeau

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

import ripyl.protocol.i2s as i2s
import ripyl.sigproc as sigp
import ripyl.streaming as streaming
import test.test_support as tsup

class TestI2SFuncs(tsup.RandomSeededTestCase):

    def test_i2s_decode(self):
        self.test_name = 'I2S message'
        self.trial_count = 50
        for i in xrange(self.trial_count):
            self.update_progress(i+1)
            
            cpol = random.choice((0, 1))
            wspol = random.choice((0, 1))
            msb_justified = random.choice((True, False))
            
            word_size = random.randint(8, 32)
            sample_rate = random.uniform(1.0e3, 1.0e7)
            channels = random.choice((1, 2))
            variant = random.choice((i2s.I2SVariant.Standard, i2s.I2SVariant.DSPModeShortSync, \
                                    i2s.I2SVariant.DSPModeLongSync))
            frame_size = random.randint(word_size, word_size * 2)
            if variant != i2s.I2SVariant.Standard:
                frame_size *= channels
            if variant == i2s.I2SVariant.DSPModeLongSync:
                frame_size += 1

            data_offset = random.randint(0, 3)
            
            msg = []
            for _ in xrange(random.randint(4, 20)):
                msg.append(random.randint(0, 2**word_size-1))
            if channels == 1 and variant == i2s.I2SVariant.Standard and len(msg) % 2 == 1:
                msg.append(random.randint(0, 2**word_size-1))
                
            if channels == 2:
                msg = list(i2s.mono_to_stereo(msg))
                
            use_edges = random.choice((True, False))

            if variant == i2s.I2SVariant.Standard:
                clock_freq = sample_rate * channels * frame_size
            else: # DSPMode
                clock_freq = sample_rate * frame_size



#            print('## msg:', msg)
#            print('## word_size:', word_size)
#            print('## frame_size:', frame_size)
#            print('## sample_rate:', sample_rate)
#            print('## cpol:', cpol)
#            print('## wspol:', wspol)
#            print('## msb_justified', msb_justified)
#            print('## channels:', channels)
#            print('## variant:', variant)
#            print('## data_offset:', data_offset)

                
            sck, sd, ws = i2s.i2s_synth(msg, word_size, frame_size, sample_rate, cpol, wspol, \
                            msb_justified, channels, variant, data_offset, idle_start=10.0/clock_freq)

            if use_edges:
                records_it = i2s.i2s_decode(sck, sd, ws, word_size, cpol, wspol, msb_justified, \
                        channels, variant, data_offset, stream_type=streaming.StreamType.Edges)

            else: # samples
                sample_period = 1.0 / (20.0 * clock_freq)
                sck_s = sigp.edges_to_sample_stream(sck, sample_period)
                sd_s = sigp.noisify(sigp.edges_to_sample_stream(sd, sample_period))
                ws_s = sigp.noisify(sigp.edges_to_sample_stream(ws, sample_period))

                records_it = i2s.i2s_decode(sck_s, sd_s, ws_s, word_size, cpol, wspol, msb_justified, \
                        channels, variant, data_offset)
                            
            records = list(records_it)
            #print('\nDecoded:', [str(r) for r in records])
            #print(records[-1].start_time, records[-1].end_time)
            
            msg_ix = 0
            match = True
            frame_cnt = 0
            for r in records:
                if r.kind == 'I2S frame':
                    frame_cnt += 1
                    #print('Data:', r.data, msg[msg_ix])
                    if r.data != msg[msg_ix]:
                        match = False
                        break
                    msg_ix += 1
                    
            self.assertTrue(match, msg='Message not decoded successfully')
            self.assertEqual(frame_cnt, len(msg), 'Missing or extra decoded messages')
                
