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

from ripyl.decode import *
import ripyl.streaming as stream
from ripyl.util.enum import Enum
from ripyl.util.bitops import *
import ripyl.sigproc as sigp


class AutoRateError(stream.StreamError):
    '''Error for failed bit rate detection'''
    pass

class CANConfig(Enum):
    '''Enumeration of configuration settings'''
    IdleHigh = 1  # Polarity settings
    IdleLow = 2


class CANTiming(object):
    def __init__(self, prop, p1, ipt=2, resync_jump=None):
        self.sync = 1
        self.prop = prop # 1-8 quanta
        self.p1 = p1 # 1-8 quanta
        self.ipt = ipt # Info. processing time is <= 2 quanta
        self.p2 = max(p1, ipt)

        self.quantum_period = 0.0 # Must call set_quantum_period() later


        self._resync_jump = resync_jump if resync_jump else min(4, self.p1)

    @property
    def resync_jump(self):
        return self._resync_jump

    @resync_jump.setter
    def resync_jump(self, value):
        # Jump is bounded between 1 and min(4, p1)
        upper_bound = min(4, self.p1)
        self._resync_jump = max(1, min(value, upper_bound))

    @property
    def total_quanta(self):
        return self.sync + self.prop + self.p1 + self.p2

    @property
    def bit_period(self):
        return self.total_quanta * self.quantum_period

    @property
    def sample_point_delay(self):
        return (self.sync + self.prop + self.p1) * self.quantum_period

    @property
    def post_sample_delay(self):
        return self.p2 * self.quantum_period

    def set_quantum_period(self, nominal_bit_period):
        self.quantum_period = nominal_bit_period / self.total_quanta
        return self.quantum_period



class CANErrorFrame(object):
    def __init__(self, flag_bits=6):
        self.flag_bits = min(max(6, flag_bits), 12)

    def get_bits(self):
        return ([0] * self.flag_bits) + ([1] * 8)

    def get_edges(self, t, bit_period):
        frame_bits = self.get_bits()
        edges = []

        for b in frame_bits:
            edges.append((t, b))
            t += bit_period

        return edges

class CANFrame(object):
    '''CAN Data and Remote frames'''
    def __init__(self, id, data, dlc=None, crc=None, ack=True):
        self.id = id
        self._rtr = None
        self.ide = 0
        self._dlc = dlc
        self.data = data
        self._crc = crc
        self.ack = ack


    @property
    def rtr(self):
        if self._rtr is None:
            return 0 if len(self.data) > 0 else 1
        else:
            return self._rtr

    @rtr.setter
    def rtr(self, value):
        self._rtr = value


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
            bits = self.get_bits()[-15:]
            return join_bits(bits)
        else:
            return self._crc

    @crc.setter
    def crc(self, value):
        self._crc = value

    def crc_is_valid(self, recv_crc=None):
        if recv_crc is None:
            recv_crc = self._crc

        data_crc = join_bits(self.get_bits()[-15:])
        
        return recv_crc == data_crc


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

    def get_edges(self, t, bit_period):
        stuffed_bits = self._bit_stuff(self.get_bits())

        # Add delimiter and ack bits
        crc_and_ack_bits = [1, 0 if self.ack else 1, 1]

        # Add EOF bits
        frame_bits = stuffed_bits + crc_and_ack_bits + [1, 1, 1, 1, 1, 1, 1]
        edges = []

        for b in frame_bits:
            edges.append((t, b))
            t += bit_period

        return edges


class CANStandardFrame(CANFrame):
    '''CAN frame format for 11-bit id'''
    def __init__(self, id, data, dlc=None, crc=None, ack=True):
        CANFrame.__init__(self, id, data, dlc, crc, ack)
        self._rtr = None
        self.ide = 0
        self.r0 = 0

    def __repr__(self):
        return 'CANStandardFrame({}, {}, {}, {}, {})'.format(hex(self.id), self.data, \
            self.dlc, hex(self.crc), 'True' if self.ack else 'False')

    def get_bits(self):
        '''Generate standard frame bits'''
        # Standard frame format:
        #  SOF, ID, RTR, IDE, r0, DLC, Data, CRC, CRC delim., ACK slot, ACK delim., EOF
        # Stuffing is applied until the CRC delimiter is reached
        
        # Generate header and data bits
        check_bits = [0] # SOF
        check_bits += split_bits(self.id, 11)
        check_bits += [self.rtr, self.ide, self.r0]
        check_bits += split_bits(self.dlc, 4)
        for b in self.data[:8]:
            check_bits += split_bits(b, 8)

        # Generate CRC
        crc_bits = can_crc15(check_bits)

        print('### Gen CRC:', crc_bits, hex(join_bits(crc_bits)))

        #ack_bits = [0 if self.ack else 1, 1]

        return check_bits + crc_bits #+ ack_bits



#FIX: implement this with CAN variants
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
    '''CAN frame format for 29-bit id'''
    def __init__(self, id, id_ext, data, dlc=None, crc=None, ack=True):
        CANFrame.__init__(self, id, data, dlc, crc, ack)
        
        self.srr = 1 # Replaces RTR bit in standard frame format; always 1
        self.ide = 1 # Always 1 for extended format
        self.id_ext = id_ext
        
        #self._rtr = None

        self.r0 = 0
        self.r1 = 0

    def __repr__(self):
        return 'CANExtendedFrame({}, {}, {}, {}, {}, {})'.format(hex(self.id), hex(self.id_ext), self.data, \
            self.dlc, hex(self.crc), 'True' if self.ack else 'False')

    def get_bits(self):
        '''Generate extended frame bits'''
        # Extended frame format:
        #  SOF, ID, SRR, IDE, ID-EXT, RTR, r1, r0, DLC, Data, CRC, CRC delim., ACK slot, ACK delim., EOF
        # Stuffing is applied until the CRC delimiter is reached
        
        # Generate header and data bits
        check_bits = [0] # SOF
        check_bits += split_bits(self.id, 11)
        check_bits += [self.srr, self.ide]
        check_bits += split_bits(self.id_ext, 18)
        check_bits += [self.rtr, self.r1, self.r0]
        check_bits += split_bits(self.dlc, 4)
        for b in self.data[:8]:
            check_bits += split_bits(b, 8)

        # Generate CRC
        crc_bits = can_crc15(check_bits)

        print('### Gen Ext CRC:', crc_bits, hex(join_bits(crc_bits)))

        return check_bits + crc_bits


class CANStreamFrame(stream.StreamSegment):
    '''Encapsulates a CANFrame object into a StreamSegment'''
    def __init__(self, bounds, frame, status=stream.StreamStatus.Ok):
        stream.StreamSegment.__init__(self, bounds, data=frame, status=status)
        self.kind = 'CAN frame'

        self.annotate('frame', {}, stream.AnnotationFormat.Hidden)


def coerce_symbol_rate(raw_symbol_rate, std_rates):
    # find the standard symbol rate closest to the raw rate
    return min(std_rates, key=lambda x: abs(x - raw_symbol_rate))



def can_decode(can, polarity=CANConfig.IdleHigh, bit_rate=None, use_std_rate=False, logic_levels=None, stream_type=stream.StreamType.Samples):
    
    if stream_type == stream.StreamType.Samples:
        if logic_levels is None:
            can_it, logic_levels = check_logic_levels(can)
        else:
            can_it = can
        
        edges = find_edges(can_it, logic_levels, hysteresis=0.4)
    else: # The stream is already a list of edges
        edges = can
        
    
    if bit_rate is None:
        # Find the bit rate
        
        # Tee off an independent iterator to determine bit rate
        edges_it, sre_it = itertools.tee(edges)
        
        min_edges = 50
        symbol_rate_edges = list(itertools.islice(sre_it, min_edges))
        
        # We need to ensure that we can pull out enough edges from the iterator slice
        if len(symbol_rate_edges) < min_edges:
            raise AutoRateError('Unable to compute automatic bit rate.')
        
        raw_symbol_rate = find_symbol_rate(iter(symbol_rate_edges), spectra=2)
        
        # Delete the tee'd iterators so that the internal buffer will not grow
        # as the edges_it is advanced later on
        #del symbol_rate_edges
        del sre_it
        
        std_rates = (10e3, 20e3, 50e3, 125e3, 250e3, 500e3, 800e3, 1e6)

        if use_std_rate:
            # find the standard rate closest to the raw rate
            bit_rate = coerce_symbol_rate(raw_symbol_rate, std_rates)
        else:
            bit_rate = raw_symbol_rate
            
    else:
        edges_it = edges

    # Invert edge polarity if idle-low
    if polarity == CANConfig.IdleLow:
        edges_it = ((t, 1 - e) for t, e in edges_it)
        
    
    bit_period = 1.0 / float(bit_rate)
    es = EdgeSequence(edges_it, bit_period)

    print('## begin CAN decode', bit_period)
    # initialize to point where state is high --> idle time before first SOF
    while es.cur_state() == 0 and not es.at_end():
        es.advance_to_edge()

    while not es.at_end():
        # look for SOF falling edge
        es.advance_to_edge()
        
        # We could have an anamolous edge at the end of the edge list
        # Check if edge sequence is complete after our advance
        if es.at_end():
            break

        # We should be at the start of the SOF
        if es.cur_state() != 0:
            continue

        start_time = es.cur_time
        dom_count = 0
        rec_count = 0
        es.advance(bit_period * 0.5) # Move to middle of SOF bit


        # Collect bits until we see a stuffing error (6 0's) or an EOF (7 1's)
        raw_bits = []
        raw_bit_times = []
        stuffing_error = False
        while True: #not es.at_end():
            raw_bits.append(es.cur_state())
            raw_bit_times.append(es.cur_time)
            if es.cur_state() == 0:
                dom_count += 1
                rec_count = 0
            else:
                rec_count += 1
                dom_count = 0

            if dom_count == 6:
                stuffing_error = True
                break

            if rec_count == 7:
                break

            es.advance(bit_period)

        if not stuffing_error: # Potentially valid frame
            print('## got frame:', stuffing_error, start_time, raw_bits)
            unstuffed_bits, stuffed_bits, stuffing_errors = _unstuff(raw_bits)
            print('##   unstuffed:', unstuffed_bits, stuffed_bits, stuffing_errors)

            std_header_bits = 1 + 12 + 6
            ext_header_bits = 1 + 32 + 6

            if len(unstuffed_bits) >= std_header_bits:
                header_bits = std_header_bits
                # Extract fields from unstuffed bits
                id_bits = unstuffed_bits[1:12]
                rtr = unstuffed_bits[12]
                ide = unstuffed_bits[13]

                field_ix = 14

                if ide == 1: # Extended format frame
                    if len(unstuffed_bits) >= ext_header_bits:
                        header_bits = ext_header_bits
                        srr = rtr
                        id_ext_bits = unstuffed_bits[field_ix:field_ix + 18]
                        field_ix += 18
                        rtr = unstuffed_bits[field_ix]
                        field_ix += 1
                        r1 = unstuffed_bits[field_ix]
                        field_ix += 1
                    else: # FIX: ERROR
                        pass

                r0 = unstuffed_bits[field_ix]
                field_ix += 1


                dlc_bits = unstuffed_bits[field_ix:field_ix + 4]
                dlc = min(join_bits(dlc_bits), 8) # Limit to max of 8 data bytes
                field_ix += 4
                data = []


                if rtr == 0: # Data frame
                    # Verify we have enough raw bits
                    min_frame_bits = header_bits + 8 * dlc + 16 + 2
                    if len(unstuffed_bits) < min_frame_bits:
                        # ERROR: short frame
                        pass #FIX
                    else:
                        for b in xrange(dlc):
                            data.append(join_bits(unstuffed_bits[field_ix:field_ix + 8]))
                            field_ix += 8
                else: # Remote frame
                    # Verify we have enough raw bits
                    min_frame_bits = header_bits + 16 + 2
                    if len(unstuffed_bits) < min_frame_bits:
                        # ERROR: short frame
                        pass #FIX


                # Get checksum
                check_bits = unstuffed_bits[field_ix:field_ix + 15]
                #print('## checksum:', hex(join_bits(check_bits)))
                field_ix += 15

                # Get ack
                ack = True if unstuffed_bits[field_ix + 1] == 0 else False
                

                #print('## id, rtr, dlc:', hex(join_bits(id_bits)), rtr, hex(join_bits(dlc_bits)))
                if ide == 0:
                    cf = CANStandardFrame(join_bits(id_bits), data, join_bits(dlc_bits), join_bits(check_bits), ack)
                else:
                    cf = CANExtendedFrame(join_bits(id_bits), join_bits(id_ext_bits), data, \
                        join_bits(dlc_bits), join_bits(check_bits), ack)

                    cf.srr = srr
                    cf.r1 = r1

                cf.rtr = rtr
                cf.ide = ide
                cf.r0 = r0 

                print('### CRC valid:', cf.crc_is_valid(), cf)

                yield CANStreamFrame((start_time, es.cur_time), cf)

        print('######## End time:', es.cur_time) 



def _unstuff(raw_bits):
    '''Remove stuffed bits from a list of bits representing a frame'''

    unstuffed = []
    dom = 0
    rec = 0
    expect_stuffing = False
    stuffing_errors = []
    stuffed_bits = []
    prev_bit = 0
    for i, b in enumerate(raw_bits):
        if not expect_stuffing:
            unstuffed.append(b)
        else:
            #print('$$ expect stuffing:', i, b, prev_bit, dom, rec)
            # Should have a stuffed bit
            if b == prev_bit: # No change from previous bit
                stuffing_errors.append(i) # This shouldn't happen except for EOF since we already filtered stuffing errors
            else: # Found a stuffed bit
                stuffed_bits.append(i)

        expect_stuffing = False

        if b == 1:
            rec += 1
            dom = 0
        else:
            dom += 1
            rec = 0
            
        if dom == 5:
            # Next bit should be a stuffed 1
            expect_stuffing = True
            dom = 0

        if rec == 5:
            # Next bit should be a stuffed 0
            expect_stuffing = True
            rec = 0

        prev_bit = b

            
    return (unstuffed, stuffed_bits, stuffing_errors)


def can_synth(frames, clock_freq, idle_start=0.0, message_interval=0.0, idle_end=0.0):
    # This is a wrapper around the actual synthesis code in _can_synth()
    # It unzips the yielded tuple and removes unwanted artifact edges
    ch, cl = itertools.izip(*_can_synth(frames, clock_freq, idle_start, message_interval, idle_end))
    ch = sigp.remove_excess_edges(ch)
    cl = sigp.remove_excess_edges(cl)

    return ch, cl

def _can_synth(frames, clock_freq, idle_start=0.0, message_interval=0.0, idle_end=0.0):
    '''Core CAN synthesizer
    
    This is a generator function.
    '''

    bit_period = 1.0 / clock_freq

    t = 0.0
    ch = 0 # tristate high
    cl = 1 # tristate low
    
    yield ((t, ch), (t, cl)) # initial conditions
    t += idle_start

    for f in frames:
        if isinstance(f, CANFrame):
            t += bit_period * 3 # Add IFS to start of data and remote frames

        edges = f.get_edges(t, bit_period)

        for e in edges:
            yield ((e[0], 0), (e[0], 1)) if e[1] else ((e[0], 1), (e[0], 0))
        
        # update time to end of edge sequence plus 3 bit periods for IFS
        t = edges[-1][0]
 
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

        
