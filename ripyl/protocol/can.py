#!/usr/bin/python
# -*- coding: utf-8 -*-

'''CAN protocol decoder
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

import itertools

#from ripyl.decode import *
#import ripyl.streaming as stream
#from ripyl.util.enum import Enum
from ripyl.util.bitops import *
import ripyl.sigproc as sigp


class CANFrame(object):
    def __init__(self, identifier, data, dlc=None, crc=None, ack=True, bit_period=1.0e-3):
        self.bit_period = bit_period
        self.identifier = identifier
        self.rtr = 0
        self.ide = 0
        self._dlc = dlc
        self.data = data
        self._crc = crc
        self.ack = ack


    @property
    def dlc(self):
        if self._dlc is None:
            return min(len(self.data), 8)
        else:
            return self._dlc

    @dlc.setter
    def dlc(self, value):
        self._dlc = value

    @property
    def crc(self):
        if self._crc is None:
            bits = self.get_bits()[-18:-3]
            return join_bits(bits)
        else:
            return self._crc

    @crc.setter
    def crc(self, value):
        self._crc = value

    def get_bits(self):
        raise NotImplementedError

    def _bit_stuff(self, bits):
        '''Perform CAN bit-stuffing'''
        sbits = []
        same_count = 0
        prev_bit = None
        for b in bits:
            sbits.append(b)

            if b == prev_bit:
                same_count += 1
            else:
                same_count = 1
                prev_bit = b

            if same_count == 5:
                # Stuff an opposite bit in the bit stream
                sbits.append(1 - b)
                same_count = 1
                prev_bit = 1 - b
        return sbits

    def get_edges(self, t):
        stuffed_bits = self._bit_stuff(self.get_bits())
        # Add EOF bits
        frame_bits = stuffed_bits + [1, 1, 1, 1, 1, 1, 1]
        edges = []

        for b in frame_bits:
            edges.append((t, b))
            t += self.bit_period

        return edges


class CANBaseFrame(CANFrame):
    '''CAN frame format for 11-bit identifier'''
    def __init__(self, identifier, data, dlc=None, crc=None, ack=True, bit_period=1.0e-3):
        CANFrame.__init__(self, identifier, data, dlc, crc, ack, bit_period)
        self.rtr = 0
        self.ide = 0
        self.r0 = 0

    def get_bits(self):
        '''Generate base frame bits'''
        # Base frame format:
        #  SOF, Identifier, RTR, IDE, r0, DLC, Data, CRC, CRC delim., ACK slot, ACK delim., EOF
        
        # Generate header and data bits
        check_bits = [0] # SOF
        check_bits += split_bits(self.identifier, 11)
        check_bits += [self.rtr, self.ide, self.r0]
        check_bits += split_bits(self.dlc, 4)
        for b in self.data[:8]:
            check_bits += split_bits(b, 8)

        # Generate CRC
        crc_bits = can_crc15(check_bits) + [1]

        print('### Gen CRC:', crc_bits[:-1], hex(join_bits(crc_bits[:-1])))

        ack_bits = [0 if self.ack else 1, 1]

        return check_bits + crc_bits + ack_bits



class ExtendedIdentifier(object):
    def __init__(self, pri, pgn, sa):
        self.pri = pri # 3-bits priority
        self.pgn = pgn # 18 bits parameter group number
        # pgn -> res (1-bit), data_page (1-bit), pdu_format, (8-bits), pdu_specific (8-bits)
        self.sa = sa   # 8-bits source address
        
    @property
    def all_bits(self):
        return (self.pri & 0x03) << 26 | (self.pgn & 0x3FFFF) << 8 | (self.sa & 0xFF)
        
    @property
    def data_page(self):
        return (self.pgn >> 16) & 0x01
        
    @data_page.setter
    def data_page(self, value):
        self.pgn = (self.pgn & 0x2FFFF) | ((value & 0x01) << 16)
        
    @property
    def pdu_format(self):
        return (self.pgn >> 8) & 0xFF

    @pdu_format.setter
    def pdu_format(self, value):
        self.pgn = (self.pgn & 0x300FF) | ((value & 0xFF) << 8)
        
    @property
    def pdu_specific(self):
        return self.pgn & 0xFF
        
    @pdu_specific.setter
    def pdu_specific(self, value):
        self.pgn = (self.pgn & 0x3FF00) | (value & 0xFF)


class CANExtendedFrame(CANFrame):
    '''CAN frame format for 29-bit identifier'''
    def __init__(self, identifier, identifier_ext, data, ack=True, bit_period=1.0e-3):
        CANFrame.__init__(self, identifier, data, ack, bit_period)
        
        self.srr = 1
        self.identifier_ext = identifier_ext
        
        self.rtr = 0
        self.ide = 1
        self.r0 = 0
        self.r1 = 0






def can_synth(frames, idle_start=0.0, message_interval=0.0, idle_end=0.0):
    # This is a wrapper around the actual synthesis code in _can_synth()
    # It unzips the yielded tuple and removes unwanted artifact edges
    ch, cl = itertools.izip(*_can_synth(frames, idle_start, message_interval, idle_end))
    ch = sigp.remove_excess_edges(ch)
    cl = sigp.remove_excess_edges(cl)

    return ch, cl

def _can_synth(frames, idle_start=0.0, message_interval=0.0, idle_end=0.0):
    '''Core CAN synthesizer
    
    This is a generator function.
    '''

    t = 0.0
    ch = 0 # tristate high
    cl = 1 # tristate low
    
    yield ((t, ch), (t, cl)) # initial conditions
    t += idle_start

    for f in frames:
        edges = f.get_edges(t)

        for e in edges:
            yield ((e[0], 0), (e[0], 1)) if e[1] else ((e[0], 1), (e[0], 0))
        
        # update time to end of edge sequence plus 3 bit periods for IFS
        t = edges[-1][0] + f.bit_period * 3
 
    ch = 0
    cl = 1
    yield ((t, ch), (t, cl))
    t += idle_end
    yield ((t, ch), (t, cl)) # final state






def can_crc15(d):
    '''Calculate CAN CRC-15 on data

    d (sequence of int)
        Array of integers representing 0 or 1 bits in transmission order
        
    Returns array of integers for each bit in the CRC with MSB first
    '''
    poly = 0x4599
    sreg = 0
    mask = 0x7fff

    crc = 0
    for b in d:
        leftbit = (sreg & 0x4000) >> 14
        sreg = (sreg << 1) & mask
        if b != leftbit:
            sreg ^= poly

    crc = sreg

    return split_bits(crc, 15)

        
