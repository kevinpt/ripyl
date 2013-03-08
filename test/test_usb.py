#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   usb.py test suite
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

        print('\n * Random seed: {} *'.format(seed))
        random.seed(seed)
        
    def test_usb_decode(self):
        trials = 50
        for i in xrange(trials):
            print('\r  USB transmission {0} / {1}  '.format(i+1, trials), end='')

            bus_speed = random.choice((usb.USBSpeed.LowSpeed, usb.USBSpeed.FullSpeed, usb.USBSpeed.HighSpeed))
            #print('\nBus speed', bus_speed)
            
            # Build a set of packets
            packet_num = random.randint(1, 10)
            #print('\nGEN PACKETS:', packet_num)
            
            
            packets = []
            for _ in xrange(packet_num):
                pid = random.randint(0,15)
                
                if bus_speed == usb.USBSpeed.LowSpeed:
                    # Never generate PRE on low-speed bus transmissions
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
                elif packet_kind == usb.USBPacketKind.Handshake or pid == usb.USBPID.PRE:
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
                
                if pid == usb.USBPID.PRE and bus_speed == usb.USBSpeed.FullSpeed:
                    # Add a Low-speed packet after the PREamble
                    pkt = usb.USBDataPacket(usb.USBPID.Data0, [1,2,3,4], speed=usb.USBSpeed.LowSpeed)
                    pkt.swap_jk = True
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
            #print('PACKETS:', len(records))
            for r in records:
                if r.kind == 'USB packet':
                    #print('  ', repr(r.packet))
                    pkt_cnt += 1
                    if r.packet != packets[pkt_ix]:
                        match = False
                        break
                    pkt_ix += 1
                else:
                    pass
                    #print('ERROR:', repr(r))
                    
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
    
    def test_usb_sample_data(self):
    
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
    