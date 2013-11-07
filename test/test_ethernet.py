#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   ethernet.py test suite
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

import ripyl.protocol.ethernet as ether
import ripyl.streaming as stream
import test.test_support as tsup


class TestEthernetFuncs(tsup.RandomSeededTestCase):

    def test_ethernet_decode(self):
        self.test_name = 'Ethernet frame'
        self.trial_count = 100
        for i in xrange(self.trial_count):
            self.update_progress(i+1)
            
            frame_count = random.randint(1, 4)
            frames = []
            data_frame_count = 0
            for i in xrange(frame_count):
                dest = [random.randint(0, 255) for _ in xrange(6)]
                source = [random.randint(0, 255) for _ in xrange(6)]
                data = [random.randint(0, 255) for _ in xrange(random.randint(64, 200))]
                frames.append(ether.EthernetFrame(dest, source, data))

            tx = ether.ethernet_synth(frames, overshoot=None, idle_start=2.0e-6, \
                                    frame_interval=(12 * 8 * 100.0e-9), idle_end=2.0e-6)

            records = list(ether.ethernet_decode(tx, stream_type=stream.StreamType.Edges))

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




