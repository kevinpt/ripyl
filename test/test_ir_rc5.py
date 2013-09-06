#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   infrared/rc5.py test suite
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
from random import randint, choice, uniform

import ripyl.protocol.infrared as ir
import ripyl.protocol.infrared.rc5 as rc5
import ripyl.sigproc as sigp
import ripyl.streaming as stream
import test.test_support as tsup

#import matplotlib.pyplot as plt

class TestRC5Funcs(tsup.RandomSeededTestCase):

    #@unittest.skip('debug')
    def test_rc5_decode(self):
        self.test_name = 'RC-5 IR protocol'
        self.trial_count = 20

        carrier_freq = 36.0e3
        sample_rate = 10.0 * carrier_freq
        rise_time = sigp.min_rise_time(sample_rate) * 1.01

        for i in xrange(self.trial_count):
            self.update_progress(i+1)

            msg_count = randint(1,10)

            msgs = []
            for i in xrange(msg_count):
                msg = rc5.RC5Message(cmd=randint(0,127), addr=randint(0,31), toggle=randint(0,1))
                msgs.append(msg)

            do_modulation = choice((True, False))


            edges = rc5.rc5_synth(msgs, message_interval=5.0e-3)
            if do_modulation:
                duty = uniform(0.1, 0.9)
                edges = ir.modulate(edges, carrier_freq, duty_cycle=duty)

            samples = sigp.synth_wave(edges, sample_rate, rise_time)
            #samples = sigp.dropout(samples, 2.6e-4, 3.8e-4)
            #samples = sigp.capacify(samples, 4.0e-7, 50.0)
            noisy = sigp.amplify(sigp.noisify(samples, snr_db=30), gain=5.0)
            waveform = list(noisy)

            #wave_samples = stream.sample_stream_to_samples(waveform)
            #plt.plot(wave_samples)
            #plt.show()

            records = list(rc5.rc5_decode(iter(waveform)))
            #print('\nDecoded {} records'.format(len(records)))

            #a = ann.Annotation(rc5.rc5_annotate(records))
            #a.print()

            self.assertEqual(len(msgs), len(records), 'Mismatch in decoded record count')

            for rec, msg in zip(records, msgs):
                self.assertEqual(rec.data, msg, 'Mismatched messages')



