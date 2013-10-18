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
import sys

import ripyl.protocol.usb as usb
import ripyl.sigproc as sigp
import ripyl.streaming as stream
import test.test_support as tsup
#from ripyl.util.bitops import join_bits


def _gen_random_usb_packet(bus_speed, allow_preamble_pid=True, allow_ext_pid=True):
    pid = random.randint(0,15)
    
    if bus_speed == usb.USBSpeed.LowSpeed or allow_preamble_pid == False:
        # Never generate PRE on low-speed bus transmissions
        while pid == usb.USBPID.PRE:
            pid = random.randint(0,15)

    if allow_ext_pid == False:
        while pid == usb.USBPID.EXT:
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

    return pkt



class TestUSBFuncs(tsup.RandomSeededTestCase):

    #@unittest.skip('debug')        
    def test_usb_decode(self):
        self.test_name = 'USB transmission'
        self.trial_count = 70
        for i in xrange(self.trial_count):
            self.update_progress(i+1)

            bus_speed = random.choice((usb.USBSpeed.LowSpeed, usb.USBSpeed.FullSpeed, usb.USBSpeed.HighSpeed))
            #print('\nBus speed', bus_speed)
            
            # Build a set of packets
            packet_num = random.randint(1, 10)
            #print('\nGEN PACKETS:', packet_num)
            
            use_protocol = random.choice(('single-ended', 'differential', 'hsic'))
            if use_protocol == 'hsic':
                bus_speed = usb.USBSpeed.HighSpeed # force bus speed for HSIC
            
            
            packets = []
            for _ in xrange(packet_num):

                packets.append(_gen_random_usb_packet(bus_speed))
                pid = packets[-1].pid
                
                if pid == usb.USBPID.PRE and bus_speed == usb.USBSpeed.FullSpeed:
                    # Add a Low-speed packet after the PREamble
                    pkt = usb.USBDataPacket(usb.USBPID.Data0, [1,2,3,4], speed=usb.USBSpeed.LowSpeed)
                    pkt.swap_jk = True
                    packets.append(pkt)

            if use_protocol == 'single-ended':
                # Synthesize edge waveforms
                dp, dm = usb.usb_synth(packets, 1.0e-7, 3.0e-7)

                # Do the decode
                records_it = usb.usb_decode(dp, dm, stream_type=stream.StreamType.Edges)
            elif use_protocol == 'differential':
                # Synthesize a differential edge waveform
                diff_d = usb.usb_diff_synth(packets, 1.0e-7, 3.0e-7)
                # Do the decode
                records_it = usb.usb_diff_decode(diff_d, stream_type=stream.StreamType.Edges)
            else: # hsic
                # Synthesize edge waveforms
                strobe, data = usb.usb_hsic_synth(packets, 1.0e-7, 3.0e-7)

                # Do the decode
                records_it = usb.usb_hsic_decode(strobe, data, stream_type=stream.StreamType.Edges)
                
            
            records = list(records_it)
            
            # Check results
            pkt_cnt = 0
            pkt_ix = 0
            match = True if len(records) > 0 else False
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
                print('\nProtocol:', use_protocol)
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



    #@unittest.skip('debugging')
    def test_usb_sample_data(self):
    
        # Read files containing 100 Full-speed SOF packets
        # Note that these packets were collected with segmented acquisition and are ~5us
        # apart rather than the proper 1ms.
        dp_samples, sample_period, start_time = tsup.read_bin_file('test/data/usb_100segs_dp.bin')
        dp_it = stream.samples_to_sample_stream(dp_samples, sample_period, start_time)

        dm_samples, sample_period, start_time = tsup.read_bin_file('test/data/usb_100segs_dm.bin')
        dm_it = stream.samples_to_sample_stream(dm_samples, sample_period, start_time)
        
        records_it = usb.usb_decode(dp_it, dm_it, stream_type=stream.StreamType.Samples)
        records = list(records_it)
        
        self.assertEqual(len(records), 100, 'Missing records, expected to decode 100')
        
        # The SOF packet frame_num fields should be monotonically increasing
        cur_frame = records[0].packet.frame_num
        for r in records[1:]:
            cur_frame += 1
            self.assertEqual(r.packet.frame_num, cur_frame, 'SOF frame_num not decoded properly')

    #@unittest.skip('debugging')  
    def test_usb_diff_sample_data(self):
    
        # Read files containing 100 Full-speed SOF packets
        # Note that these packets were collected with segmented acquisition and are ~5us
        # apart rather than the proper 1ms.
        dp_samples, sample_period, start_time = tsup.read_bin_file('test/data/usb_100segs_dp.bin')
        dp_it = stream.samples_to_sample_stream(dp_samples, sample_period, start_time)

        dm_samples, sample_period, start_time = tsup.read_bin_file('test/data/usb_100segs_dm.bin')
        dm_it = stream.samples_to_sample_stream(dm_samples, sample_period, start_time)
        
        # generate differential waveform
        d_diff_it = sigp.sum_streams(dp_it, sigp.invert(dm_it))
        
        records_it = usb.usb_diff_decode(d_diff_it, stream_type=stream.StreamType.Samples)
        records = list(records_it)
        
        self.assertEqual(len(records), 100, 'Missing records, expected to decode 100')
        
        # The SOF packet frame_num fields should be monotonically increasing
        cur_frame = records[0].packet.frame_num
        for r in records[1:]:
            cur_frame += 1
            self.assertEqual(r.packet.frame_num, cur_frame, 'SOF frame_num not decoded properly')

    #@unittest.skip('debug')
    def test_usb_crc16(self):
        import ripyl.util.bitops as bitops
        self.test_name = 'USB CRC-16'
        self.trial_count = 1000
        for i in xrange(self.trial_count):
            self.update_progress(i+1)

            data_size = random.randint(1,30)
            data = [random.randint(0,255) for _ in xrange(data_size)]

            b_data = []
            for d in data:
                b_data.extend(reversed(bitops.split_bits(d, 8)))

            crc16 = bitops.join_bits(reversed(usb.usb_crc16(b_data)))
            tcrc16 = bitops.join_bits(reversed(usb.table_usb_crc16(data)))

            if crc16 != tcrc16:
                print('\nMismatch: {}, {}, {},  {}'.format(hex(crc16), hex(tcrc16), hex(ncrc16), data))

            self.assertEqual(crc16, tcrc16, 'CRC-16 mismatch')


    #@unittest.skip('debug')
    def test_usb_field_offsets(self):
        # This test exercises the field_offsets() code and verifies that the
        # packet CRCs are in the right position
        self.test_name = 'USB field offsets'
        self.trial_count = 1000
        for i in xrange(self.trial_count):
            self.update_progress(i+1)
        
            bus_speed = random.choice((usb.USBSpeed.LowSpeed, usb.USBSpeed.FullSpeed, usb.USBSpeed.HighSpeed))
            pkt = _gen_random_usb_packet(bus_speed, allow_preamble_pid=False, allow_ext_pid=False)
            
            #pkt = usb.USBTokenPacket(usb.USBPID.PING, 0x79, 0x7, 1)
            #USBDataPacket(MData, [145, 145, 218, 206, 69, 160, 119], 1, 0.0)
            #USBSOFPacket(SOF, 0x7a, 2, 0.0)
            #pkt = usb.USBDataPacket(usb.USBPID.Data0, [123, 104, 182, 44, 238], 2, 0.0) # stuffing in CRC
            #pkt = usb.USBTokenPacket(usb.USBPID.TokenIn, 0x7e, 0xf, 0, 0.0) # stuffing in CRC, bad adjustment


            offsets = pkt.field_offsets(with_stuffing=False)
            s_offsets = pkt.field_offsets(with_stuffing=True)

            #print('##  offsets:', offsets)
            #print('## s offsets:', s_offsets)

            original_bits = pkt.get_bits()
            stuffed_bits = pkt._bit_stuff(original_bits)
            unstuffed_bits, stuffed_bit_indices, _ = usb._unstuff(stuffed_bits)
            sop_bits = pkt.sop_bits();

            if 'CRC16' in offsets:
                crc = original_bits[-16:]

                
                s_crc_bounds = s_offsets['CRC16']
                stuffed_crc = stuffed_bits[s_crc_bounds[0] + sop_bits:s_crc_bounds[1] + sop_bits + 1]

                crc_bounds = offsets['CRC16']
                unstuffed_crc = unstuffed_bits[crc_bounds[0] + sop_bits:crc_bounds[1] + sop_bits + 1]
                #print('CRC-16', crc, unstuffed_crc, stuffed_crc, crc_bounds, s_crc_bounds)
                #print('  bits:', original_bits)
                #print('s bits:', stuffed_bits)
                #print('u bits:', unstuffed_bits)

            elif 'CRC5' in offsets:
                crc = original_bits[-5:]

                s_crc_bounds = s_offsets['CRC5']
                stuffed_crc = stuffed_bits[s_crc_bounds[0] + sop_bits:s_crc_bounds[1] + sop_bits + 1]

                crc_bounds = offsets['CRC5']
                unstuffed_crc = unstuffed_bits[crc_bounds[0] + sop_bits:crc_bounds[1] + sop_bits + 1]

                #print('CRC-5', crc, unstuffed_crc, stuffed_crc, crc_bounds, s_crc_bounds)
                #print('  bits:', original_bits)
                #print('s bits:', stuffed_bits)
                #print('u bits:', unstuffed_bits)

                #stuff_pos = pkt._bit_stuff_offsets(pkt.get_bits())
                #print('stuff pos', stuff_pos)
                #unstuffed_offsets = pkt.field_offsets()
                #print('unstuffed offsets', unstuffed_offsets)
                #adj_offsets = dbg_adjust_stuffing(pkt, pkt.field_offsets())
                #print('adj offsets', adj_offsets)
            else:
                continue

            self.assertEqual(crc, unstuffed_crc, 'unstuffed CRC mismatch')

            if s_crc_bounds[1] - s_crc_bounds[0] == crc_bounds[1] - crc_bounds[0]:
                # No stuffing in CRC itself so we can compare values
                #print('#### stuffed bounds, unstuffed bounds:', s_crc_bounds, crc_bounds, s_crc_bounds[1] - s_crc_bounds[0], crc_bounds[1] - crc_bounds[0], hex(join_bits(crc)), hex(join_bits(stuffed_crc)))
                self.assertEqual(crc, stuffed_crc, 'stuffed CRC mismatch')


