#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   lin.py test suite
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

import ripyl.protocol.lin as lin
import ripyl.streaming as stream
import test.test_support as tsup

class TestLINFuncs(tsup.RandomSeededTestCase):

    def test_lin_decode(self):
        self.test_name = 'LIN frame'
        self.trial_count = 100
        for i in xrange(self.trial_count):
            self.update_progress(i+1)
            
            frame_count = random.randint(3, 6)
            frames = []

            # We will randomly decide which ids use enhanced checksum
            id_cs_type = [random.choice((lin.LINChecksum.Classic, lin.LINChecksum.Enhanced)) for _ in xrange(0x40)]

            # IDs 60 and 61 always use classic checksums
            id_cs_type[60] = lin.LINChecksum.Classic
            id_cs_type[61] = lin.LINChecksum.Classic

            # Collect the enhanced ids together
            enhanced_ids = [i for i, t in enumerate(id_cs_type) if t == lin.LINChecksum.Enhanced]


            for i in xrange(frame_count):

                lin_id = random.randint(0, 50)

                data_count = random.randint(0,8)

                data = [random.randint(0,0xFF) for b in xrange(data_count)]

                frames.append(lin.LINFrame(lin_id, data, cs_type=id_cs_type[lin_id]))

            baud = random.randint(1000, 20000)

            # These frames lack a second harmonic in the edge stream
            #frames = [
            #    lin.LINFrame(21, [7, 188, 161], None, None, 1),
            #    lin.LINFrame(4, [250, 65, 40, 175, 8, 192, 32, 86], None, None, 1),
            #    lin.LINFrame(13, [119, 94, 5], None, None, 1)
            #]
            #baud = 18989

            # These frames lack a second harmonic in the edge stream (from seed 465994505)
            #frames = [
            #    lin.LINFrame(16, None, None, None, 0),
            #    lin.LINFrame(48, None, None, None, 1),
            #    lin.LINFrame(4, [131, 195, 187, 28, 235], None, None, 0),
            #    lin.LINFrame(25, [108, 73, 209, 162], None, None, 1),
            #    lin.LINFrame(1, [214, 209], None, None, 0)
            #]

            #baud = 10000

            edges = lin.lin_synth(frames, baud, frame_interval=10.0 / baud, \
                idle_start=4.0 / baud, idle_end=8.0 / baud, byte_interval=3.0 / baud)
            
            param_info = {}
            records = list(lin.lin_decode(edges, enhanced_ids=None, baud_rate=None, \
                stream_type=stream.StreamType.Edges, param_info=param_info))


            #if param_info['baud_rate'] < 1000:
            #print('### original frames:')
            #for o in frames:
            #    print('  ', o, o.cs_type)
            #print('### decoded frames:')
            #for r in records:
            #    print('  ', r.data, r.data.cs_type)

            self.assertRelativelyEqual(baud, param_info['baud_rate'], 0.01, \
                'Decoded incorrect baud rate {} -> {}'.format(baud, param_info['baud_rate']))

            self.assertEqual(len(records), len(frames), 'Decoded frame count mismatch: {} -> {}'.format(len(frames), len(records)))

            for r, o in zip(records, frames):
                if r.data != o:
                    print('Mismatch:\n  {}\n  {}'.format(o, r.data))
                self.assertEqual(r.data, o, 'Frames are different')
            

