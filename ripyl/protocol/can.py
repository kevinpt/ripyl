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
from copy import copy


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
    '''CAN Error frame'''
    def __init__(self, flag_bits=6, ifs_bits=0):
        self.flag_bits = min(max(6, flag_bits), 12)
        self.ifs_bits = max(0, ifs_bits)

    def __repr__(self):
        return 'CANErrorFrame({}, {})'.format(self.flag_bits, self.ifs_bits)

    def __str__(self):
        return '(error)'

    def get_edges(self, t, bit_period):
        edges = []

        if self.ifs_bits > 0:
            edges.append((t, 1))
            t += self.ifs_bits * bit_period

        edges.append((t, 0))

        t += self.flag_bits * bit_period
        edges.append((t, 1))

        t += 8 * bit_period
        edges.append((t, 1))

        return edges


    def __eq__(self, other):
        return isinstance(other, CANErrorFrame) and str(self) == str(other)

    def __ne__(self, other):
        return not (self == other)


class CANOverloadFrame(CANErrorFrame):
    '''CAN Overload frame'''
    def __init__(self, flag_bits=6, ifs_bits=0):
        CANErrorFrame.__init__(self, flag_bits, ifs_bits)

    def __repr__(self):
        return 'CANOverloadFrame({}, {})'.format(self.flag_bits, self.ifs_bits)

    def __str__(self):
        return '(overload)'



class CANFrame(object):
    '''CAN Data and Remote frames'''
    def __init__(self, id, data, dlc=None, crc=None, ack=True, trim_bits=0, ifs_bits=3):
        self.id = id
        self._rtr = None
        self.ide = 0
        self._dlc = dlc
        self.data = data
        self._crc = crc
        self.ack = ack
        self.trim_bits = trim_bits
        self.ifs_bits=ifs_bits


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
        for i, b in enumerate(bits):
            sbits.append(b)

            if b == prev_bit:
                same_count += 1
            else:
                same_count = 1
                prev_bit = b

            if same_count == 5 and i < len(bits)-1: #FIX: verify that a final stuffed bit should be suppressed
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

        if self.trim_bits > 0:
            trimmed_bits = frame_bits[:-self.trim_bits]
            frame_bits = frame_bits[:-self.trim_bits]

        edges = []

        for b in frame_bits:
            edges.append((t, b))
            t += bit_period

        return edges

    def __eq__(self, other):
        if not isinstance(other, CANFrame): return False

        s_vars = copy(vars(self))
        s_vars['_rtr'] = self.rtr
        s_vars['_dlc'] = self.dlc
        s_vars['_crc'] = self.crc

        o_vars = copy(vars(other))
        o_vars['_rtr'] = other.rtr
        o_vars['_dlc'] = other.dlc
        o_vars['_crc'] = other.crc

        del s_vars['trim_bits']
        del s_vars['ifs_bits']
        del o_vars['trim_bits']
        del o_vars['ifs_bits']

        #print('### eq s:', s_vars)
        #print('### eq o:', o_vars)

        return s_vars == o_vars


    def __ne__(self, other):
        return not (self == other)

    @property
    def full_id(self):
        return self.id & 0x7FF



class CANStandardFrame(CANFrame):
    '''CAN frame format for 11-bit id'''
    def __init__(self, id, data, dlc=None, crc=None, ack=True, trim_bits=0, ifs_bits=3):
        CANFrame.__init__(self, id, data, dlc, crc, ack, trim_bits, ifs_bits)
        self._rtr = None
        self.ide = 0
        self.r0 = 0

    def __repr__(self):
        return 'CANStandardFrame({}, {}, {}, {}, {}, {}, {})'.format(hex(self.id), self.data, \
            self.dlc, hex(self.crc), 'True' if self.ack else 'False', self.trim_bits, self.ifs_bits)

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

        #ack_bits = [0 if self.ack else 1, 1]

        return check_bits + crc_bits #+ ack_bits


class CANExtendedFrame(CANFrame):
    '''CAN frame format for 29-bit id'''
    def __init__(self, full_id, data, dlc=None, crc=None, ack=True, trim_bits=0, ifs_bits=3):
        CANFrame.__init__(self, (full_id >> 18) & 0x7FF, data, dlc, crc, ack, trim_bits, ifs_bits)
        
        self.srr = 1 # Replaces RTR bit in standard frame format; always 1
        self.ide = 1 # Always 1 for extended format
        self.id_ext = full_id & 0x3FFFF
        
        self.r0 = 0
        self.r1 = 0

    def __repr__(self):
        return 'CANExtendedFrame({}, {}, {}, {}, {}, {}, {})'.format(hex(self.full_id), self.data, \
            self.dlc, hex(self.crc), 'True' if self.ack else 'False', self.trim_bits, self.ifs_bits)

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

        return check_bits + crc_bits

    @property
    def full_id(self):
        return ((self.id & 0x7FF) << 18) + (self.id_ext & 0x3FFFF)



can_variant = {
    'J1939': (('priority', (28, 26)), ('r', (25, 25)), ('dp', (24, 24)), ('pf', (23, 16)), ('ps', (15, 8)), ('sa', (7, 0))),
    'CANOpen': (('fc', (10, 7)), ('nid', (6, 0)))
}


def can_id(variant, **kwargs):
    '''Generate a CAN ID for a protocol variant from separate fields'''
    if variant not in can_variant:
        raise ValueError('Invalid CAN variant "{}"'.format(variant))

    field_bounds = dict(can_variant[variant])
    field_names = [f[0] for f in can_variant[variant]]
    field_vals = dict(zip(field_names, [0]*len(field_names)))

    for k, v in kwargs.iteritems():
        if k not in field_vals:
            raise ValueError('Invalid field name "{}"'.format(k))

        field_vals[k] = v

    id = 0
    for fn in field_names:
        v = field_vals[fn]
        bounds = field_bounds[fn]
        flen = bounds[0] - bounds[1] + 1

        mask = 2**flen - 1
        if v > mask:
            raise ValueError('Value too large for field "{}", {}'.format(fn, v))

        id <<= flen
        id += v & mask

    return id
        


class CANStreamStatus(Enum):
    '''Enumeration for CANStreamFrame status codes'''
    ShortFrameError  = stream.StreamStatus.Error + 1
    BitStuffingError = stream.StreamStatus.Error + 2
    CRCError         = stream.StreamStatus.Error + 3
    AckError         = stream.StreamStatus.Error + 4

class CANStreamFrame(stream.StreamSegment):
    '''Encapsulates a CANFrame object into a StreamSegment'''
    def __init__(self, bounds, frame, field_info=None, stuffed_bits=None, status=stream.StreamStatus.Ok):
        stream.StreamSegment.__init__(self, bounds, data=frame, status=status)
        self.kind = 'CAN frame'
        self.stuffed_bits = stuffed_bits
        self.field_info = field_info

        self.annotate('frame', {}, stream.AnnotationFormat.Hidden)


def _coerce_symbol_rate(raw_symbol_rate, std_rates):
    # Find the standard symbol rate closest to the raw rate
    return min(std_rates, key=lambda x: abs(x - raw_symbol_rate))

_can_field_formats = {
    'id': ('addr', stream.AnnotationFormat.Hex),
    'id_ext': ('addr', stream.AnnotationFormat.Hex),
    'crc': ('check', stream.AnnotationFormat.Hex),
    'ack': ('ack', stream.AnnotationFormat.Hidden),
    'r0': ('misc', stream.AnnotationFormat.Hidden),
    'r1': ('misc', stream.AnnotationFormat.Hidden),
    'data': ('data', stream.AnnotationFormat.Hex),
}


std_header_bits = 1 + 12 + 6
ext_header_bits = 1 + 32 + 6


class _BitExtractor(object):
    def __init__(self, es, bit_period):
        self.es = es
        self.bit_period = bit_period
        self.dom_count = 0
        self.rec_count = 0
        self.expect_stuffing = False
        self.dom_start_time = 0.0
        self.raw_bit_count = 0
        self.stuffed_bits = []
        self.prev_bit = 0

    def advance_to_falling(self):
        while not self.es.at_end():
            # look for SOF falling edge
            self.es.advance_to_edge()
            
            # We could have an anamolous edge at the end of the edge list
            # Check if edge sequence is complete after our advance
            if self.es.at_end():
                break

            # We should be at the start of the SOF
            if self.es.cur_state() != 0:
                continue
            else:
                break

        self.dom_count = 1
        self.rec_count = 0
        self.expect_stuffing = False
        self.dom_start_time = self.es.cur_time
        self.raw_bit_count = 0
        self.stuffed_bits = []
        self.prev_bit = 0

    def get_bits(self, num_bits, unstuff=True):
        extract_bits = []
        last_bit = False

        if self.es.at_end():
            return extract_bits

        while len(extract_bits) < num_bits:
            edge_span = self.es.next_states[0] - self.es.cur_states[0]
                
            if self.es.cur_state() == 0 and edge_span >= 5.5 * self.bit_period:
                break

            if unstuff:
                if not self.expect_stuffing:
                    extract_bits.append(self.es.cur_state())

                elif self.es.cur_state() != self.prev_bit: # Found a stuffed bit
                    self.stuffed_bits.append(self.raw_bit_count)

                self.expect_stuffing = False

                if self.dom_count == 5: # Next bit should be a stuffed 1
                    self.expect_stuffing = True
                    self.dom_count = 0
                elif self.rec_count == 5: # Next bit should be a stuffed 0
                    self.expect_stuffing = True
                    self.rec_count = 0
                    
            else: # No unstuffing
                extract_bits.append(self.es.cur_state())


            if self.es.next_states[0] < self.es.cur_time + self.bit_period: # Adjust for timing drift
                half_bit_err = self.es.cur_time - (self.es.next_states[0] - (self.bit_period / 2)) #FIX
                advance_time = self.bit_period - half_bit_err
            else:
                advance_time = self.bit_period

            self.prev_bit = self.es.cur_state()
            self.es.advance(advance_time)
            self.raw_bit_count += 1

            if self.es.cur_state() == 1:
                self.rec_count += 1
                self.dom_count = 0
            else:
                self.dom_count += 1
                self.rec_count = 0

                if self.dom_count == 1:
                    self.dom_start_time = self.es.cur_time - self.bit_period / 2 #FIX bit timing

            if last_bit:
                break

            if self.es.at_end():
                last_bit = True

        return extract_bits



can_std_bit_rates = (10e3, 20e3, 50e3, 125e3, 250e3, 500e3, 800e3, 1e6)


def can_decode(can, polarity=CANConfig.IdleHigh, bit_rate=None, coerce_rates=None, logic_levels=None, stream_type=stream.StreamType.Samples):
    
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
            raise AutoRateError('Unable to compute automatic bit rate. Insufficient edges.')
        
        raw_symbol_rate = find_symbol_rate(iter(symbol_rate_edges), spectra=2)

        # Delete the tee'd iterators so that the internal buffer will not grow
        # as the edges_it is advanced later on
        del symbol_rate_edges
        del sre_it
        
        if coerce_rates:
            # find the standard rate closest to the raw rate
            bit_rate = _coerce_symbol_rate(raw_symbol_rate, coerce_rates)
        else:
            bit_rate = raw_symbol_rate

        if bit_rate == 0:
            raise AutoRateError('Unable to compute automatic bit rate. Got 0.')

        #print('### decoded bit rate:', bit_rate)
            
    else:
        edges_it = edges

    # Invert edge polarity if idle-low
    if polarity == CANConfig.IdleLow:
        edges_it = ((t, 1 - e) for t, e in edges_it)
        
    
    bit_period = 1.0 / float(bit_rate)
    es = EdgeSequence(edges_it, bit_period)

    be = _BitExtractor(es, bit_period)

    # initialize to point where state is high --> idle time before first SOF
    while es.cur_state() == 0 and not es.at_end():
        es.advance_to_edge()

    while not es.at_end():
        # look for SOF falling edge
        #es.advance_to_edge()

        be.advance_to_falling()
        # We are now at a potential SOF
        
        # We could have an anamolous edge at the end of the edge list
        # Check if edge sequence is complete after our advance
        if es.at_end():
            break


        start_time = es.cur_time
        es.advance(bit_period * 0.5) # Move to middle of SOF bit #FIX

        unstuffed_bits = be.get_bits(std_header_bits)

        stuffing_error = True if len(unstuffed_bits) < std_header_bits and not es.at_end() else False

        # If a data or remote frame ends with an error frame we will get a stuffing error.
        # If the error happens in the EOF field, the frame is still recoverable.
        # If a stuffing error occures in the last-but-one bit of the EOF it is regarded as an overload frame.

        found_data_rmt_frame = False

        field_info = []

        if len(unstuffed_bits) >= std_header_bits:
            found_data_rmt_frame = True
            header_bits = std_header_bits
            # Extract fields from unstuffed bits
            id_bits = unstuffed_bits[1:12]; field_info.append(('id', (1,11)))
            rtr = unstuffed_bits[12]; field_info.append(('rtr', (12, 12)))
            ide = unstuffed_bits[13]; field_info.append(('ide', (13, 13)))

            field_ix = 14

            if ide == 1: # Extended format frame
                unstuffed_bits += be.get_bits(ext_header_bits - std_header_bits)
                if len(unstuffed_bits) >= ext_header_bits:
                    header_bits = ext_header_bits
                    srr = rtr
                    id_ext_bits = unstuffed_bits[field_ix:field_ix + 18]; field_info.append(('id_ext', (field_ix, field_ix+17)))
                    field_ix += 18
                    rtr = unstuffed_bits[field_ix]; field_info.append(('rtr', (field_ix, field_ix)))
                    field_info[1] = ('srr', (12, 12))
                    field_ix += 1
                    r1 = unstuffed_bits[field_ix]; field_info.append(('r1', (field_ix, field_ix)))
                    field_ix += 1
                else:
                    # ERROR: short extended frame
                    # Not enough bits to have partially decoded frame. Just abort
                    #print('### short extended frame:', len(unstuffed_bits), ext_header_bits)
                    continue

            r0 = unstuffed_bits[field_ix]; field_info.append(('r0', (field_ix, field_ix)))
            field_ix += 1


            dlc_bits = unstuffed_bits[field_ix:field_ix + 4]; field_info.append(('dlc', (field_ix, field_ix+3)))
            dlc = min(join_bits(dlc_bits), 8) # Limit to max of 8 data bytes
            field_ix += 4
            data = []

            if rtr == 0: # Data frame
                remaining_stuffed_bits = 8 * dlc + 15
            else: # Remote frame
                remaining_stuffed_bits = 15

            min_frame_bits = header_bits + remaining_stuffed_bits

            unstuffed_bits += be.get_bits(remaining_stuffed_bits)

            short_frame = False
            if rtr == 0: # Data frame
                # Verify we have enough raw bits
                if len(unstuffed_bits) < min_frame_bits:
                    # ERROR: short frame
                    short_frame = True
                else: # Get data bytes
                    for b in xrange(dlc):
                        data.append(join_bits(unstuffed_bits[field_ix:field_ix + 8]))
                        field_info.append(('data', (field_ix, field_ix+7)))
                        field_ix += 8
            else: # Remote frame
                # Verify we have enough raw bits
                if len(unstuffed_bits) < min_frame_bits:
                    # ERROR: short frame
                    #print('### short remote frame', len(unstuffed_bits), min_frame_bits, unstuffed_bits, stuffed_bits)
                    short_frame = True

            check_bits = []
            ack = 1
            if not short_frame:
                # Get checksum
                check_bits = unstuffed_bits[field_ix:field_ix + 15]; field_info.append(('crc', (field_ix, field_ix+14)))
                field_ix += 15

                # The remaining fields (crc delim, ack, ack delim) are not stuffed
                end_bits = be.get_bits(3, unstuff=False)
                if len(end_bits) == 3:
                    ack = True if end_bits[1] == 0 else False
                else:
                    ack = False

                    # The last frame of the stream requires special treatment
                    # To position ourselves after the ack delim.
                    if es.cur_state() == 1:
                        es.advance((2 - len(end_bits)) * bit_period)

                field_info.append(('ack', (field_ix+1, field_ix+1)))


            if ide == 0:
                cf = CANStandardFrame(join_bits(id_bits), data, join_bits(dlc_bits), join_bits(check_bits), ack)
            else:
                cf = CANExtendedFrame(join_bits(id_bits + id_ext_bits), data, \
                    join_bits(dlc_bits), join_bits(check_bits), ack)

                cf.srr = srr
                cf.r1 = r1

            cf.rtr = rtr
            cf.ide = ide
            cf.r0 = r0 


            # Determine the end of the frame
            if es.cur_state() == 1:
                if es.cur_time > es.next_states[0]:
                    # Special case for last frame in stream
                    end_time = es.cur_time + 5.5 * bit_period
                elif es.next_states[0] > es.cur_time + 5 * bit_period: #FIX
                    end_time = es.cur_time + 5.5 * bit_period
                else:
                    end_time = es.next_states[0]
                    stuffing_error = True
                    es.advance_to_edge()
                    be.dom_start_time = es.cur_time

            else: # Aready in dominant state
                end_time = be.dom_start_time
                stuffing_error = True

            sf = CANStreamFrame((start_time, end_time), cf, field_info, be.stuffed_bits)

            if short_frame:
                sf.annotate('frame_bad', {}, stream.AnnotationFormat.Hidden)
                sf.status = CANStreamStatus.ShortFrameError

            # Add subrecords for each field in the frame
            adj_info = _adjust_fields_for_stuffing(field_info, be.stuffed_bits)

            field_sizes = [e - s + 1 for _, (s, e) in field_info]

            data_ix = 0
            for (field, bit_bounds), field_size in zip(adj_info, field_sizes):
                bounds = (start_time + bit_bounds[0] * bit_period, start_time + (bit_bounds[1] + 1) * bit_period)


                if field in _can_field_formats:
                    style, text_format = _can_field_formats[field]
                else:
                    style = 'ctrl'
                    text_format = stream.AnnotationFormat.Hex

                value = getattr(cf, field)
                if field == 'data':
                    value = value[data_ix]
                    data_ix += 1

                status = stream.StreamStatus.Ok
                if field == 'crc' and not cf.crc_is_valid():
                    status = CANStreamStatus.CRCError
                if field == 'ack' and not cf.ack:
                    status = CANStreamStatus.AckError


                sf.subrecords.append(stream.StreamSegment(bounds, value, kind=field, status=status))
                sf.subrecords[-1].annotate(style, {'_bits':field_size}, text_format)

            yield sf

        # Check if the EOF was complete

        if stuffing_error:
            # This could be an error or overload frame

            # Keep fetching dominant bits until they become recessive. Then look for 8 recessive delimiter bits.
            while es.cur_state() == 0 and not es.at_end():
                es.advance(bit_period)

            if es.cur_time < es.next_states[0]:
                end_time = es.next_states[0]
            else: # Special case for end of stream
                end_time = es.cur_time + 7 * bit_period

            if end_time - es.cur_time > 6.5 * bit_period: # Valid error or overload frame
                es.advance(7 * bit_period)

                if found_data_rmt_frame:
                    # There was an error frame following a data or remote frame
                    cf = CANErrorFrame()
                else:
                    cf = CANOverloadFrame()
                end_time = es.cur_time + 0.5 * bit_period # FIX
                sf = CANStreamFrame((be.dom_start_time, end_time), cf)
                sf.annotate('frame', {'name':''}, stream.AnnotationFormat.String)
                yield sf


def _stuffed_index(stuffed_bits, ix):
    '''Return the adjusted bit index with correction for stuffed bits'''
    real_ix = 0
    eff_ix = -1

    while True:
        if real_ix not in stuffed_bits:
            eff_ix += 1

        if eff_ix == ix:
            break

        real_ix += 1

    return real_ix

def _adjust_fields_for_stuffing(field_info, stuffed_bits):
    '''Correct field positions for presence of stuffed bits'''

    if len(stuffed_bits) == 0: # No bit stuffing present
        return field_info

    adj_info = []
    for field, (start, end) in field_info:
        start = _stuffed_index(stuffed_bits, start)
        end = _stuffed_index(stuffed_bits, end)

        adj_info.append((field, (start, end)))

    return adj_info



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

    if isinstance(frames[0], CANErrorFrame) and idle_start == 0.0 and frames[0].ifs_bits == 0:
        # The first frame is an error or overload with no IFS bits. Start inverted from idle.
        ch = 1
        cl = 0
    else: # Idle
        ch = 0 # tristate high
        cl = 1 # tristate low
    
    yield ((t, ch), (t, cl)) # initial conditions
    t += idle_start

    for f in frames:
        if isinstance(f, CANFrame):
            t += bit_period * f.ifs_bits # Add IFS to start of data and remote frames

        edges = f.get_edges(t, bit_period)

        for e in edges:
            yield ((e[0], 0), (e[0], 1)) if e[1] else ((e[0], 1), (e[0], 0))
        
        # Update time to end of edge sequence
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


