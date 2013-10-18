#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   can.py test suite
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

import ripyl.protocol.can as can
import ripyl.streaming as stream
import test.test_support as tsup

def gen_random_can_frame():
    use_extended = random.choice((True, False))
    if use_extended:
        can_id = random.randrange(0, 2**29)
    else:
        can_id = random.randrange(0, 2**11)

    data_count = random.randint(0,8)

    data = [random.randint(0,0xFF) for b in xrange(data_count)]

    ack_bit = random.choice((True, False))

    if use_extended:
        cf = can.CANExtendedFrame(can_id, data, ack=ack_bit)
    else:
        cf = can.CANStandardFrame(can_id, data, ack=ack_bit)

    return cf


class TestCANFuncs(tsup.RandomSeededTestCase):

    def test_can_decode(self):
        self.test_name = 'CAN frame'
        self.trial_count = 100
        for i in xrange(self.trial_count):
            self.update_progress(i+1)
            
            frame_count = random.randint(3, 6)
            frames = []
            data_frame_count = 0
            for i in xrange(frame_count):

                use_ovl = random.random() < 0.1

                if use_ovl:
                    flag_bits = random.randint(6, 12)
                    frames.append(can.CANOverloadFrame(flag_bits, ifs_bits=0))

                else: # data and remote frames
                    frames.append(gen_random_can_frame())
                    data_frame_count += 1

                    use_err = random.random() < 0.1
                    if use_err:
                        flag_bits = random.randint(6, 12)
                        frames.append(can.CANErrorFrame(flag_bits, ifs_bits=0))
                        frames[-2].trim_bits = random.randint(1,5)

            if data_frame_count < 3:
                # Generate additional data and remote frames to help ensure there are enough
                # edges for auto rate detection.
                for i in xrange(3 - data_frame_count):
                    frames.append(gen_random_can_frame())

            clock_freq = random.randint(10e3, 1e6)

            ch, cl = can.can_synth(frames, clock_freq, idle_start=1.0e-5)

            records = list(can.can_decode(cl, stream_type=stream.StreamType.Edges))

            self.assertEqual(len(records), len(frames), 'Decoded frame count mismatch: {} -> {}'.format(len(frames), len(records)))

            for r, o in zip(records, frames):
                if r.data != o:
                    print('Mismatch:\n  {}\n  {}'.format(o, r.data))

                    print('### original frames:', clock_freq)
                    for o in frames:
                        print('  ', repr(o))

                    print('### decoded frames:')
                    for r in records:
                        print('  ', repr(r.data))
                self.assertEqual(r.data, o, 'Frames are different')
            

