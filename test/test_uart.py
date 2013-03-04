#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Protocol decode library
   uart.py test suite
'''

# Copyright © 2013 Kevin Thibedeau

# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:

# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
from __future__ import print_function, division

import unittest
import random
from collections import deque

import ripyl.protocol.uart as uart
import ripyl.sigproc as sigp

class TestUARTFuncs(unittest.TestCase):
    def setUp(self):
        import time
        import os
        
        # Use seed from enviroment if it is set
        try:
            seed = long(os.environ['TEST_SEED'])
        except KeyError:
            random.seed()
            seed = long(random.random() * 1e9)

        print('\n  Random seed:', seed)
        random.seed(seed)
        
    def test_uart_decode(self):
        print('')
        trials = 10
        for i in xrange(trials):
            print('\r  UART message {0} / {1}  '.format(i+1, trials), end='')
            
            msg = []
            for _ in xrange(20):
                msg.append(chr(random.choice(xrange(ord('0'), ord('z')) )))
                
            msg = ''.join(msg)
            
            #baud = random.randrange(50000, 200000)
            baud = random.choice((110, 300, 600, 1200, 2400, 4800, 9600, 14400, 19200, 28800, 38400, \
            56000, 57600, 115200, 128000, 153600, 230400, 256000, 460800, 921600))
            
            #baud = 56000
            
            sample_rate = baud * 100.0
            rise_time = 0.35 * 2.0 / sample_rate * 10.0 # 10x min rise time
            #print('!!!!!!!!!!!!!!! baud:', baud, rise_time)
            parity = random.choice((None, 'even', 'odd'))
            
            bits = random.choice((7, 8, 9))
            #print('!!!!!!!!!!!!! bits:', bits)
            
            edges = uart.uart_synth(bytearray(msg), bits, baud, parity=parity, idle_start=100.0 / sample_rate)
            
            samples = sigp.synth_wave(edges, sample_rate, rise_time, ripple_db=60)
            
            noisy = sigp.amplify(sigp.noisify(samples, snr_db=20.0), gain=-15.0)
            waveform = list(noisy)
            bd = deque()
            frames = uart.uart_decode(iter(waveform), bits=bits, inverted=False, parity=parity, baud_rate=None, baud_deque=bd)
            frames = list(frames)
            #print('@@@@ deque data:', bd.pop())
            #print(''.join(str(d) for d in frames))
            decoded_msg = ''.join(str(d) for d in frames)
            
            self.assertEqual(msg, decoded_msg, \
                "Message not decoded successfully msg:'{0}', baud:{1}, parity:{2}, bits:{3}".format(msg, \
                baud, parity, bits))
            
