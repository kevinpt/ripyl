#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   streaming.py test suite
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
import os

import ripyl.streaming as stream
import test.test_support as tsup

class TestStreamingFuncs(tsup.RandomSeededTestCase):

    def test_save_stream(self):
        self.test_name = 'save_stream() test'
        self.trial_count = 40

        out_dir = os.path.join('test', 'test-output')
        if not os.path.exists(out_dir):
            os.mkdir(out_dir)

        save_file = os.path.join(out_dir, 'test_save_stream.bin')

        for i in xrange(self.trial_count):
            self.update_progress(i+1)

            rec_count = random.randint(0,4)

            records = []
            
            for r in xrange(rec_count):
                rnd_kind = ''.join([chr(random.randrange(ord('a'), ord('z')+1)) for _ in xrange(4)])
                rec = stream.StreamRecord(kind=rnd_kind, status = random.randint(0,1000))
                records.append(rec)

                srec_count = random.randint(0,4)
                for sr in xrange(srec_count):
                    rnd_kind = ''.join([chr(random.randrange(ord('a'), ord('z')+1)) for _ in xrange(4)])
                    srec = stream.StreamRecord(kind=rnd_kind, status = random.randint(0,1000))
                    rec.subrecords.append(srec)


            stream.save_stream(records, save_file)
            saved_recs = stream.load_stream(save_file)

            self.assertEqual(len(records), len(saved_recs), 'Mismatch record rount')

            if len(records) == len(saved_recs):
                for r,s in zip(records, saved_recs):
                    self.assertEqual(r, s, 'Mismatched records')


