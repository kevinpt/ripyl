#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   uart.py test suite
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
from collections import deque
import sys

import ripyl.protocol.uart as uart
import ripyl.sigproc as sigp
import ripyl.streaming as stream
import test.test_support as tsup


class TestUARTFuncs(unittest.TestCase):
    def setUp(self):
        import os
        
        # Use seed from enviroment if it is set
        try:
            seed = long(os.environ['TEST_SEED'])
        except KeyError:
            random.seed()
            seed = long(random.random() * 1e9)

        print('\n * Random seed: {} *'.format(seed))
        random.seed(seed)

    #@unittest.skip('debug')
    def test_uart_decode(self):
        trials = 10
        for i in xrange(trials):
            print('\r  UART message {0} / {1}  '.format(i+1, trials), end='')
            sys.stdout.flush()
            
            msg = []
            for _ in xrange(20):
                msg.append(chr(random.choice(xrange(ord('0'), ord('z')) )))
                
            msg = ''.join(msg)
            
            baud = random.choice((110, 300, 600, 1200, 2400, 4800, 9600, 14400, 19200, 28800, 38400, \
            56000, 57600, 115200, 128000, 153600, 230400, 256000, 460800, 921600))
            
            sample_rate = baud * 100.0
            rise_time = 0.35 * 2.0 / sample_rate * 10.0 # 10x min rise time
            parity = random.choice((None, 'even', 'odd'))
            
            bits = random.choice((7, 8, 9))
            
            #print('\nTRIAL {}: msg="{}", baud={}, parity={}, bits={}'.format(i, msg, baud, parity, bits))
            
            edges = uart.uart_synth(bytearray(msg.encode('utf-8')), bits, baud, parity=parity, idle_start=100.0 / sample_rate)
            
            samples = sigp.synth_wave(edges, sample_rate, rise_time, ripple_db=60)
            
            noisy = sigp.amplify(sigp.noisify(samples, snr_db=20), gain=-15.0)
            waveform = list(noisy)
            bd = deque()
            frames = uart.uart_decode(iter(waveform), bits=bits, polarity=uart.UARTConfig.IdleLow, parity=parity, baud_rate=None, baud_deque=bd)
            frames = list(frames)
            #print('@@@@ deque data:', bd.pop())
            #print(''.join(str(d) for d in frames))
            decoded_msg = ''.join(str(d) for d in frames)
            
            self.assertEqual(msg, decoded_msg, \
                "Message not decoded successfully msg:'{0}', baud:{1}, parity:{2}, bits:{3}".format(msg, \
                baud, parity, bits))
            
    def test_uart_hello(self):
    
        bits = 8
        polarity = uart.UARTConfig.IdleLow
        parity = 'even'
        stop_bits = 2
        message = 'Hello, world!'

        samples, sample_period, start_time = tsup.read_bin_file('test/data/uart_hello_8e2.bin')
        txd = sigp.samples_to_sample_stream(samples, sample_period, start_time)
        frames = list(uart.uart_decode(txd, bits=bits, polarity=polarity, parity=parity, stop_bits=stop_bits))
        
        ok_status = True
        for f in frames:
            if f.nested_status() != stream.StreamStatus.Ok:
                ok_status = False
                break
                
        self.assertTrue(ok_status, 'Decoded data has non-Ok status')
        
        # Check the message bytes
        dmsg = ''.join([chr(d.data) for d in frames])
        self.assertEqual(message, dmsg, 'Message mismatch. Expected: "{}" Got: "{}"'.format(message, dmsg))
            

        bits = 8
        polarity = uart.UARTConfig.IdleLow
        parity = None
        stop_bits = 1
        message = 'Hello, world!'

        samples, sample_period, start_time = tsup.read_bin_file('test/data/uart_hello.bin')
        txd = sigp.samples_to_sample_stream(samples, sample_period, start_time)
        frames = list(uart.uart_decode(txd, bits=bits, polarity=polarity, parity=parity, stop_bits=stop_bits))
        
        ok_status = True
        for f in frames:
            if f.nested_status() != stream.StreamStatus.Ok:
                ok_status = False
                break
                
        self.assertTrue(ok_status, 'Decoded data has non-Ok status')
        
        # Check the message bytes
        dmsg = ''.join([chr(d.data) for d in frames])
        self.assertEqual(message, dmsg, 'Message 2 mismatch. Expected: "{}" Got: "{}"'.format(message, dmsg))
