#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Protocol decode library
   usb.py test suite
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

import ripyl.protocol.usb as usb
import ripyl.sigproc as sigp
import ripyl.streaming as streaming
import test_support as tsup

class TestUSBFuncs(unittest.TestCase):
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
        
    def XXtest_usb_decode(self):
        print('')
        trials = 1
        for i in xrange(trials):
            print('\r  USB transmission {0} / {1}  '.format(i+1, trials), end='')

            bus_speed = random.choice((usb.USBSpeed.LowSpeed, usb.USBSpeed.FullSpeed, usb.USBSpeed.HighSpeed))
            print('\nBus speed', bus_speed)
            #bus_speed = usb.USBSpeed.FullSpeed
            
            # Build a set of packets
            packet_num = random.randint(1, 10)
            #packet_num = 2
            print('\nGEN PACKETS:', packet_num)
            
            
            packets = []
            for _ in xrange(packet_num):
                pid = random.randint(0,15)
                while pid == usb.USBPID.PRE:
                    pid = random.randint(0,15)
                    
                packet_kind = usb._get_packet_kind(pid)
                
                if packet_kind == usb.USBPacketKind.Token or pid == usb.USBPID.PING:
                    if pid != usb.USBPID.SOF:
                        addr = random.randint(0, 0x7F)
                        endp = random.randint(0, 0xF)
                        pkt = usb.USBTokenPacket(pid, addr, endp, speed=bus_speed)
                    else:
                        addr = random.randint(0, 0x7F)
                        pkt = usb.USBSOFPacket(pid, addr, speed=bus_speed)
                elif packet_kind == usb.USBPacketKind.Data:
                    data_len = random.randint(1, 10)
                    data = [random.randint(0, 255) for d in xrange(data_len)]
                    pkt = usb.USBDataPacket(pid, data, speed=bus_speed)
                elif packet_kind == usb.USBPacketKind.Handshake:
                    pkt = usb.USBHandshakePacket(pid, speed=bus_speed)
                else:
                    if pid == usb.USBPID.SPLIT:
                        addr = random.randint(0, 0x7F)
                        sc = random.choice((0, 1))
                        port = random.randint(0, 0x7F)
                        s = random.choice((0, 1))
                        e = random.choice((0, 1))
                        et = random.randint(0, 3)
                        pkt = usb.USBSplitPacket(pid, addr, sc, port, s, e, et, speed=bus_speed)
                    else: #EXT
                        addr = random.randint(0, 0x7F)
                        endp = random.randint(0, 0xF)
                        sub_pid = random.randint(0, 0xF)
                        variable = random.randint(0, 0x3FF)
                        pkt = usb.USBEXTPacket(pid, addr, endp, sub_pid, variable, speed=bus_speed)
            
                packets.append(pkt)

                
            # Synthesize edge waveforms
            dp, dm = zip(*list(usb.usb_synth(packets, 1.0e-7, 3.0e-7)))
            dp = list(sigp.remove_excess_edges(iter(dp)))
            dm = list(sigp.remove_excess_edges(iter(dm)))            
            
            # Do the decode
            records_it = usb.usb_decode(iter(dp), iter(dm), stream_type=streaming.StreamType.Edges)
            
            records = list(records_it)
            
            # Check results
            pkt_cnt = 0
            pkt_ix = 0
            match = True
            print('PACKETS:', len(records))
            for r in records:
                if r.kind == 'USB packet':
                    print('  ', repr(r.packet))
                    pkt_cnt += 1
                    if r.packet != packets[pkt_ix]:
                        match = False
                        break
                    pkt_ix += 1
                else:
                    print('ERROR:', repr(r))
                    
            if not match:
                print('\nOriginal packets:')
                for p in packets:
                    print('  ', p)

                print('\nDecoded packets:')
                for r in records:
                    if r.kind == 'USB packet':
                        print('  ', r.packet)
                    else:
                        print('  ', repr(r), r.status)
                
            self.assertTrue(match, msg='Packets not decoded successfully')
            self.assertEqual(pkt_cnt, len(packets), \
                'Missing or extra decoded packets (got {} , expected {})'.format(pkt_cnt, len(packets)))
    
    def XXtest_usb_sample_data(self):
    
        # Read files containing 100 Full-speed SOF packets
        # Note that these packets were collected with segmented acquisition and are ~5us
        # apart rather than the proper 1ms.
        dp_samples, sample_period = tsup.read_bin_file('test/data/usb_100segs_dp.bin')
        dm_samples, sample_period = tsup.read_bin_file('test/data/usb_100segs_dm.bin')
        
        time_samples = [i*sample_period for i in xrange(len(dp_samples))]
        
        dp_s = zip(time_samples, dp_samples)
        dm_s = zip(time_samples, dm_samples)
        
        records_it = usb.usb_decode(iter(dp_s), iter(dm_s), stream_type=streaming.StreamType.Samples)
        records = list(records_it)
        
        self.assertEqual(len(records), 100, 'Missing records, expected to decode 100')
        
        # The SOF packet frame_num fields should be monotonically increasing
        cur_frame = records[0].packet.frame_num
        for r in records[1:]:
            cur_frame += 1
            self.assertEqual(r.packet.frame_num, cur_frame, 'SOF frame_num not decoded properly')
  
    def test_usb_diff_sample_data(self):
    
        # Read files containing 100 Full-speed SOF packets
        # Note that these packets were collected with segmented acquisition and are ~5us
        # apart rather than the proper 1ms.
        dp_samples, sample_period = tsup.read_bin_file('test/data/usb_100segs_dp.bin')
        dm_samples, sample_period = tsup.read_bin_file('test/data/usb_100segs_dm.bin')
        
        time_samples = [i*sample_period for i in xrange(len(dp_samples))]
        
        # generate differential waveform
        d_diff_samples = [s[0] - s[1] for s in zip(dp_samples, dm_samples)]
        
        d_diff_s = zip(time_samples, d_diff_samples)
        
        records_it = usb.usb_diff_decode(iter(d_diff_s), stream_type=streaming.StreamType.Samples)
        records = list(records_it)
        
        self.assertEqual(len(records), 100, 'Missing records, expected to decode 100')
        
        # The SOF packet frame_num fields should be monotonically increasing
        cur_frame = records[0].packet.frame_num
        for r in records[1:]:
            cur_frame += 1
            self.assertEqual(r.packet.frame_num, cur_frame, 'SOF frame_num not decoded properly')  
    