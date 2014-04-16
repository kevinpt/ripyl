#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   j1850.py test suite
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

import ripyl.protocol.j1850 as j1850
import ripyl.streaming as stream
import test.test_support as tsup


def gen_j1850_frame(break_thresh=0.1):

    gen_break = True if random.random() < break_thresh else False

    if gen_break:
        return j1850.J1850Break()


    priority = random.randint(0, 7)
    msg_type = random.choice((0, 1, 2, 3, 4, 8, 9, 10, 11, 12, 14))

    single_byte_hdr = random.choice((True, False))

    if single_byte_hdr:
        target = None
        source = None
    else:
        target = random.randint(0, 255)
        source = random.randint(0, 255)

    data = [random.randint(0, 255) for _ in xrange(random.randint(0, 6))]
    if len(data) == 0: data = None

    ifr_data=None
    if msg_type < 8: # Need IFR
        ifr_data = [random.randint(0, 255) for _ in xrange(random.randint(1, 6))]

    f = j1850.J1850Frame(priority, msg_type, data, target, source, ifr_data)

    return f

    

class TestJ1850Funcs(tsup.RandomSeededTestCase):

    #@unittest.skip('debug')
    def test_j1850_vpw_decode(self):
        self.test_name = 'J1850 VPW frame'
        self.trial_count = 100
        for i in xrange(self.trial_count):
            self.update_progress(i+1)

            frame_count = random.randint(1, 6)
            frames = []
            for i in xrange(frame_count):
                frames.append(gen_j1850_frame())

            norm_bit = random.choice((j1850.VPWNormBitStyle.SAE, j1850.VPWNormBitStyle.GM))
            vpw = j1850.j1850_vpw_synth(frames, norm_bit=norm_bit)

            records = list(j1850.j1850_vpw_decode(vpw, norm_bit=norm_bit, stream_type=stream.StreamType.Edges))

            self.assertEqual(len(records), len(frames), 'Decoded frame count mismatch: {} -> {}'.format(len(frames), len(records)))

            for r, o in zip(records, frames):
                if r.data != o:
                    print('Mismatch:\n  {}\n  {}'.format(o, r.data))

                    print('### original frames:')
                    for o in frames:
                        print('  ', repr(o))

                    print('### decoded frames:')
                    for r in records:
                        print('  ', repr(r.data))
                self.assertEqual(r.data, o, 'Frames are different')

    #@unittest.skip('debugging')
    def test_j1850_pwm_decode(self):
        self.test_name = 'J1850 PWM frame'
        self.trial_count = 100
        for i in xrange(self.trial_count):
            self.update_progress(i+1)

            frame_count = random.randint(1, 6)
            frames = []
            for i in xrange(frame_count):
                frames.append(gen_j1850_frame())

            pwm_p, pwm_m = j1850.j1850_pwm_synth(frames)

            records = list(j1850.j1850_pwm_decode(pwm_p, stream_type=stream.StreamType.Edges))

            self.assertEqual(len(records), len(frames), 'Decoded frame count mismatch: {} -> {}'.format(len(frames), len(records)))

            for r, o in zip(records, frames):
                if r.data != o:
                    print('Mismatch:\n  {}\n  {}'.format(o, r.data))

                    print('### original frames:')
                    for o in frames:
                        print('  ', repr(o))

                    print('### decoded frames:')
                    for r in records:
                        print('  ', repr(r.data))
                self.assertEqual(r.data, o, 'Frames are different')


    #@unittest.skip('debugging')
    def test_j1850_sample_data(self):
    
        # Read files containing frames
        dp_samples, sample_period, start_time = tsup.read_bin_file('test/data/j1850_pwm_1p.bin')
        dp_it = stream.samples_to_sample_stream(dp_samples, sample_period, start_time)

        records = list(j1850.j1850_pwm_decode(dp_it))
        
        #print('### decoded records:', len(records))
        #for r in records:
        #    print(r.data)
        self.assertEqual(len(records), 9, 'Missing records, expected to decode 9')
        

