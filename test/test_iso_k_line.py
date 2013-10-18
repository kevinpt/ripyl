#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   iso_k_line.py test suite
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

import ripyl.protocol.iso_k_line as kline
import ripyl.sigproc as sigp
import ripyl.streaming as stream
import test.test_support as tsup

class TestKLineFuncs(tsup.RandomSeededTestCase):

    def test_kline_decode(self):
        self.test_name = 'K-line message'
        self.trial_count = 10
        for i in xrange(self.trial_count):
            self.update_progress(i+1)
            
            msg_count = random.randint(1, 6)
            messages = []

            for i in xrange(msg_count):
                data_bytes = random.randint(0,6)

                protocol = random.choice((kline.KLineProtocol.ISO9141, kline.KLineProtocol.ISO14230))
                if protocol == kline.KLineProtocol.ISO9141:
                    # ISO9141 request
                    msg = [0x68, 0x6A, 0xF1]
                else:
                    header_size = random.choice((3, 4))
                    if header_size == 3:
                        msg = [0x80 + data_bytes+1, 0xD1, 0xF1]
                    else:
                        msg = [0x80, data_bytes+1, 0xD1, 0xF1]

                sid = random.randint(0, 0x3F)
                msg.append(sid)
                
                msg.extend([random.randint(0,0xFF) for b in xrange(data_bytes)])
                cs = sum(msg) % 256
                msg.append(cs)
                messages.append(msg)

                data_bytes = random.randint(0,6)
                if protocol == kline.KLineProtocol.ISO9141:
                    # ISO9141 response
                    msg = [0x48, 0x6B, 0xD1]
                else:
                    if header_size == 3:
                        msg = [0x80 + data_bytes+1, 0xF1, 0xD1]
                    else:
                        msg = [0x80, data_bytes+1, 0xF1, 0xD1]

                msg.append(sid + 0x40)
                msg.extend([random.randint(0,0xFF) for b in xrange(data_bytes)])
                cs = sum(msg) % 256
                msg.append(cs)
                messages.append(msg)


            baud = 10400
            
            sample_rate = baud * 100.0
            rise_time = sigp.min_rise_time(sample_rate) * 10.0 # 10x min rise time
            
            edges = kline.iso_k_line_synth(messages, idle_start=8.0 / baud, idle_end=8.0 / baud)
            
            samples = sigp.synth_wave(edges, sample_rate, rise_time, ripple_db=60)
            
            noisy = sigp.amplify(sigp.noisify(samples, snr_db=20), gain=12.0)
            waveform = list(noisy)

            records_it = kline.iso_k_line_decode(iter(waveform))
            records = list(records_it)

            raw_decode = []
            for r in records:
                msg = r.msg.header.bytes() + r.msg.data + [r.msg.checksum]
                raw_decode.append([b.data for b in msg])

            msg_match = True
            for msg, omsg in zip(raw_decode, messages):
                if msg != omsg:
                    msg_match = False
                    break

            
            self.assertTrue(msg_match, "Messages not decoded successfully")
            

