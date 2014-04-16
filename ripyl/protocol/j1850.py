#!/usr/bin/python
# -*- coding: utf-8 -*-

'''J1850 protocol decoder
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

from copy import copy

import itertools
#import ripyl.util.eng as eng
import ripyl.streaming as stream
import ripyl.decode as decode
import ripyl.sigproc as sigp
from ripyl.util.enum import Enum
from ripyl.util.bitops import split_bits, join_bits


# J2178 defines three message formats:
#  1-byte              H-bit is ignored -> all 256 values available for header
#  consolidated 1-byte H-bit = 1
#  consolidates 3-byte H-bit = 0


class J1850MT(Enum):
    '''Enumeration of J1850 message types (last 4 bits of header byte)'''
# K-bit = 0 (IFR required PWM/Ford)
    Function = 0
    Broadcast = 1
    FunctionQuery = 2
    FunctionRead = 3    # Only message type with CRC on IFR

    # Physical addressing
    NodeToNodeIFR = 4

    Reserved5 = 5
    Reserved6 = 6
    Reserved7 = 7

# K-bit = 1 (no IFR VPW/GM)
    FunctionCmd = 8
    FunctionRqst = 9
    FunctionExtCmd = 10
    FunctionExtRqst = 11

    # Physical addressing
    NodeToNode = 12
    Reserved13 = 13
    Ack = 14
    Reserved15 = 15


class VPWNormBitStyle(Enum):
    '''Enumeration of VPW normalization bit coding scheme'''
    SAE = 1  # short NB = No IFR CRC; long NB = IFR CRC
    GM =  2  # long NB = No IFR CRC; short NB = IFR CRC


class J1850Frame(object):
    '''Base class for J1850 frames'''
    def __init__(self, priority, msg_type, data, target=None, source=None, ifr_data=None, crc=None, ifr_crc=None):
        '''
        priority (int)
            The 3-bit frame priority field. Lower values have higher priority.

        msg_type (J1850MT)
            Message type.

        data (sequence of int or None)
            Data bytes for the frame.

        target (int)
            Target address or function.

        source (int)
            Source address.

        ifr_data (sequence of int or None)
            Optional data for the In-Frame Response.

        crc (int or None)
            CRC for the data bytes and header.

        ifr_crc (int or None)
            CRC for the IFR (FunctionRead message type only)
        '''
        self.priority = priority
        self.msg_type = msg_type
        self.data = data
        self.target = target
        self.source = source
        self.ifr_data = ifr_data
        self._crc = crc
        self._ifr_crc = ifr_crc

    def __repr__(self):
        crc = hex(self._crc) if self._crc is not None else None
        ifr_crc = hex(self._ifr_crc) if self._ifr_crc is not None else None
        return 'J1850Frame({}, {}, {}, {}, {}, {}, {}, {})'.format(self.priority, hex(self.msg_type), self.data, \
            self.target, self.source, self.ifr_data, crc, ifr_crc)


    def __eq__(self, other):
        if not isinstance(other, J1850Frame): return False

        s_vars = copy(vars(self))
        s_vars['_crc'] = self.crc
        s_vars['_ifr_crc'] = self.ifr_crc

        o_vars = copy(vars(other))
        o_vars['_crc'] = other.crc
        o_vars['_ifr_crc'] = other.ifr_crc


        #print('## s_vars:')
        #for k in sorted(s_vars.iterkeys()):
        #    print('  {}: {}'.format(k, s_vars[k]))
        #print('## o_vars:')
        #for k in sorted(o_vars.iterkeys()):
        #    print('  {}: {}'.format(k, o_vars[k]))

        return s_vars == o_vars


    def __ne__(self, other):
        return not (self == other)

    @property
    def crc(self):
        if self._crc is None:
            return self.bytes[-1]
        else:
            return self._crc

    @crc.setter
    def crc(self, value):
        self._crc = value

    @property
    def ifr_crc(self):
        if self._ifr_crc is None:
            ib = self.ifr_bytes
            if len(ib) > 0:
                return ib[-1]
            else:
                return None
        else:
            return self._ifr_crc

    @ifr_crc.setter
    def ifr_crc(self, value):
        self._ifr_crc = value


    @property
    def bytes(self):
        '''Get the bytes for this frame. Does not include IFR.'''
        header_len = 0 if self.target is not None and self.source is not None else 0x10
        header = (self.msg_type & 0x0F) + header_len + ((self.priority & 0x7) << 5)
        
        if header_len != 0: # 1-byte header
            header_bytes = [header]
        else: # 3-byte header
            header_bytes = [header, self.target, self.source]

        check_bytes = header_bytes
        if self.data is not None: check_bytes += self.data

        crc = table_j1850_crc8(check_bytes)

        return check_bytes + [crc]


    def crc_is_valid(self, recv_crc=None):
        '''Check if a decoded CRC is valid.

        recv_crc (int or None)
            The decoded CRC to check against. If None, the CRC passed in the constructor is used.

        Returns True when the CRC is correct.
        '''
        if recv_crc is None:
            recv_crc = self._crc

        data_crc = self.bytes[-1]
        
        return recv_crc == data_crc


    @property
    def ifr_bytes(self):
        '''Get the IFR bytes for this frame.'''
        check_bytes = []
        if self.ifr_data is not None: check_bytes += self.ifr_data

        if len(check_bytes) > 0:
            crc = table_j1850_crc8(check_bytes)
            return check_bytes + [crc]
        else:
            return []

    def ifr_crc_is_valid(self, recv_crc=None):
        '''Check if a decoded IFR CRC is valid.

        recv_crc (int or None)
            The decoded CRC to check against. If None, the CRC passed in the constructor is used.

        Returns True when the CRC is correct.
        '''
        if recv_crc is None:
            recv_crc = self._ifr_crc

        ifr_data_crc = self.ifr_bytes[-1]
        
        return recv_crc == ifr_data_crc


class J1850Break(object):
    '''Representation of a J1850 break condition'''
    def __init__(self):
        pass

    def __repr__(self):
        return 'J1850Break()'

    def __eq__(self, other):
        if not isinstance(other, J1850Break): return False
        return True

    def __ne__(self, other):
        return not (self == other)




class J1850StreamStatus(Enum):
    '''Enumeration for J1850StreamFrame status codes'''
    CRCError         = stream.StreamStatus.Error + 1


class J1850StreamFrame(stream.StreamSegment):
    '''Encapsulates a J1850Frame object into a StreamSegment'''
    def __init__(self, bounds, frame, status=stream.StreamStatus.Ok):
        stream.StreamSegment.__init__(self, bounds, data=frame, status=status)
        self.kind = 'J1850 frame'

        self.annotate('frame', {}, stream.AnnotationFormat.Hidden)



def j1850_vpw_decode(vpw, norm_bit=VPWNormBitStyle.SAE, logic_levels=None, stream_type=stream.StreamType.Samples):
    '''Decode a J1850 VPW data stream

    This decodes the Variable Pulse Width version of J1850 (GM & Chrysler).

    This is a generator function that can be used in a pipeline of waveform
    procesing operations.

    Sample streams are a sequence of SampleChunk Objects. Edge streams are a sequence
    of 2-tuples of (time, int) pairs. The type of stream is identified by the stream_type
    parameter. Sample streams will be analyzed to find edge transitions representing
    0 and 1 logic states of the waveforms. With sample streams, an initial block of data
    is consumed to determine the most likely logic levels in the signal.

    vpw (iterable of SampleChunk objects or (float, int) pairs)
        A sample stream or edge stream representing a VPW data signal.

    norm_bit (VPWNormBitStyle)
        How to interpret the normalization bit for In-Frame Response. Either standard SAE
        style or the GM specific variant. This determines whether the IFR is expected to
        have a CRC independently from the message type.

    logic_levels ((float, float) or None)
        Optional pair that indicates (low, high) logic levels of the sample
        stream. When present, auto level detection is disabled. This has no effect on
        edge streams.
    
    stream_type (streaming.StreamType)
        A StreamType value indicating that the can parameter represents either Samples
        or Edges

    Yields a series of J1850StreamFrame objects. Each frame contains subrecords marking the location
      of sub-elements within the frame. CRC errors are recorded as an error status in their
      respective subrecords.
      
    Raises AutoLevelError if stream_type = Samples and the logic levels cannot
      be determined.
    '''

    if stream_type == stream.StreamType.Samples:
        if logic_levels is None:
            vpw_it, logic_levels = decode.check_logic_levels(vpw)
        else:
            vpw_it = vpw
        
        edges = decode.find_edges(vpw_it, logic_levels, hysteresis=0.4)
    else: # The stream is already a list of edges
        edges = vpw

    es = decode.EdgeSequence(edges, 0.0)

    while not es.at_end():
        # Look for start of frame
        es.advance_to_edge()

        if es.cur_state() != 1: continue

        frame_start = es.cur_time

        if es.next_states[0] > es.cur_time:
            pulse_width = es.next_states[0] - es.cur_time
        else:
            pulse_width = 500.0e-6

        if 163.0e-6 < pulse_width <= 239.0e-6: # This is a valid SOF
            es.advance_to_edge() # Move to first bit
        else:
            if pulse_width > 280.0e-6 and es.cur_state() == 1:
                brk = J1850Break()
                sf = stream.StreamSegment((es.cur_time, es.next_states[0]), brk, kind='break')
                sf.annotate('frame', {'value':'Break'}, stream.AnnotationFormat.String)
                yield sf

            continue


        def collect_bits(es):
            '''Find frame and IFR bits'''
            frame_bits = []
            bit_starts = []
            is_passive = 1

            if es.next_states[0] > es.cur_time:
                pulse_width = es.next_states[0] - es.cur_time
            else:
                pulse_width = 500.0e-6

            while pulse_width <= 239.0e-6:

                if 34.0e-6 < pulse_width <= 163.0e-6:
                    if pulse_width > 96.0e-6: # 128us pulse
                        b = 1 if is_passive else 0
                    else: # 64us pulse
                        b = 0 if is_passive else 1

                    frame_bits.append(b)
                    bit_starts.append(es.cur_time)
                    is_passive = 1 - is_passive

                elif pulse_width > 163.0e-6: # EOD
                    break
                else: # Invalid pulse < 34us
                    break

                es.advance_to_edge()
                if es.next_states[0] > es.cur_time:
                    pulse_width = es.next_states[0] - es.cur_time
                else:
                    pulse_width = 500.0e-6

            bit_starts.append(es.cur_time)

            return (frame_bits, bit_starts, pulse_width)

        # Get the frame bits
        frame_bits, bit_starts, pulse_width = collect_bits(es)
        if pulse_width > 280.0e-6 and es.cur_state() == 1:
            brk = J1850Break()
            sf = stream.StreamSegment((es.cur_time, es.next_states[0]), brk, kind='break')
            sf.annotate('frame', {'value':'Break'}, stream.AnnotationFormat.String)
            yield sf
            continue

        # Validate collected bits
        if len(frame_bits) % 8 != 0 or len(frame_bits) < 2 * 8:
            continue

        # Convert frame bits to bytes
        bytes = []
        for i in xrange(len(frame_bits) // 8):
            bytes.append(join_bits(frame_bits[i*8:i*8+8]))

        byte_starts = bit_starts[::8]

        header_len = 1 if bytes[0] & 0x10 else 3
        if header_len == 3 and len(bytes) < 4: continue


        priority = bytes[0] >> 5
        msg_type = bytes[0] & 0x0F
        data = bytes[header_len:-1]
        if len(data) == 0: data = None

        # Look for IFR
        if es.next_states[0] > es.cur_time:
            pulse_width = es.next_states[0] - es.cur_time
        else:
            pulse_width = 500.0e-6

        ifr_bytes = []
        ifr_byte_starts = []
        ifr_with_crc = False
        if 200.0e-6 < pulse_width <= 280.0e-6 and (msg_type & 0x08) == 0:
            # IFR is present
            # Check normalization bit width to determine if IFR CRC is present
            es.advance_to_edge() # Start of norm bit
            if es.next_states[0] > es.cur_time:
                pulse_width = es.next_states[0] - es.cur_time
            else:
                pulse_width = 500.0e-6

            if norm_bit == VPWNormBitStyle.SAE:
                ifr_with_crc = True if pulse_width > 96.0e-6 else False
            else: # GM
                ifr_with_crc = True if pulse_width <= 96.0e-6 else False

            es.advance_to_edge() # Move to first bit

            # Get the IFR bits
            ifr_bits, ifr_bit_starts, pulse_width = collect_bits(es)
            if pulse_width > 280.0e-6 and es.cur_state() == 1:
                brk = J1850Break()
                sf = stream.StreamSegment((es.cur_time, es.next_states[0]), brk, kind='break')
                sf.annotate('frame', {'value':'Break'}, stream.AnnotationFormat.String)
                yield sf
                continue

            # Validate IFR bits
            if len(ifr_bits) % 8 == 0 and len(ifr_bits) >= 8:
                # Convert IFR bits to bytes
                for i in xrange(len(ifr_bits) // 8):
                    ifr_bytes.append(join_bits(ifr_bits[i*8:i*8+8]))

                ifr_byte_starts = ifr_bit_starts[::8]


        sf = _build_j1850_record(bytes, ifr_bytes, byte_starts, ifr_byte_starts, ifr_with_crc, (frame_start, es.cur_time + 64.0e-6))
        yield sf



def j1850_pwm_decode(pwm, logic_levels=None, stream_type=stream.StreamType.Samples):
    '''Decode a J1850 PWM data stream

    This decodes the Pulse Width Modulated version of J1850 (Ford).

    This is a generator function that can be used in a pipeline of waveform
    procesing operations.

    Sample streams are a sequence of SampleChunk Objects. Edge streams are a sequence
    of 2-tuples of (time, int) pairs. The type of stream is identified by the stream_type
    parameter. Sample streams will be analyzed to find edge transitions representing
    0 and 1 logic states of the waveforms. With sample streams, an initial block of data
    is consumed to determine the most likely logic levels in the signal.

    pwm (iterable of SampleChunk objects or (float, int) pairs)
        A sample stream or edge stream representing a PWM Bus+ signal or the differential
        Bus+ - Bus-.

    logic_levels ((float, float) or None)
        Optional pair that indicates (low, high) logic levels of the sample
        stream. When present, auto level detection is disabled. This has no effect on
        edge streams.
    
    stream_type (streaming.StreamType)
        A StreamType value indicating that the can parameter represents either Samples
        or Edges

    Yields a series of J1850StreamFrame objects. Each frame contains subrecords marking the location
      of sub-elements within the frame. CRC errors are recorded as an error status in their
      respective subrecords.
      
    Raises AutoLevelError if stream_type = Samples and the logic levels cannot
      be determined.
    '''

    if stream_type == stream.StreamType.Samples:
        if logic_levels is None:
            pwm_it, logic_levels = decode.check_logic_levels(pwm)
        else:
            pwm_it = pwm
        
        edges = decode.find_edges(pwm_it, logic_levels, hysteresis=0.4)
    else: # The stream is already a list of edges
        edges = pwm

    es = decode.EdgeSequence(edges, 0.0)

    while not es.at_end():
        # Look for start of frame
        es.advance_to_edge()

        if es.cur_state() != 1: continue

        frame_start = es.cur_time

        if es.next_states[0] > es.cur_time:
            pulse_width = es.next_states[0] - es.cur_time
        else:
            pulse_width = 500.0e-6

        if 27.0e-6 <= pulse_width <= 34.0e-6: # This is a valid SOF pulse (Tp7)
            sof_start = es.cur_time
            es.advance_to_edge() # Move to end of SOF pulse
            if es.next_states[0] > es.cur_time:
                pulse_width = es.next_states[0] - es.cur_time
            else:
                pulse_width = 500.0e-6

            if 42.0e-6 <= es.cur_time - sof_start + pulse_width <= 54.0e-6:
                # Valid SOF (Tp4)
                es.advance_to_edge() # Move to first bit
            
        else: # Look for break condition
            if 34.0e-6 < pulse_width <= 43.0e-6 and es.cur_state() == 1:
                brk = J1850Break()
                sf = stream.StreamSegment((es.cur_time, es.next_states[0]), brk, kind='break')
                sf.annotate('frame', {'value':'Break'}, stream.AnnotationFormat.String)
                yield sf

            continue

        def collect_bits(es):
            '''Find frame and IFR bits'''
            frame_bits = []
            bit_starts = []

            if es.next_states[0] > es.cur_time:
                pulse_width = es.next_states[0] - es.cur_time
            else:
                pulse_width = 500.0e-6

            while pulse_width <= 18.0e-6:
                if 4.0e-6 <= pulse_width <= 18.0e-6:
                    if pulse_width <= 10.0e-6:
                        b = 1
                    else:
                        b = 0

                    frame_bits.append(b)
                    bit_starts.append(es.cur_time)

                    bit_pulse = pulse_width
                    # Move to end of pulse
                    es.advance_to_edge()
                    if es.next_states[0] > es.cur_time:
                        pulse_width = es.next_states[0] - es.cur_time
                    else:
                        pulse_width = 500.0e-6

                    tp3 = bit_pulse + pulse_width
                    if 21.0e-6 <= tp3 <= 27e-6: # Valid bit
                        es.advance_to_edge() # Move to start of next bit
                        if es.next_states[0] > es.cur_time:
                            pulse_width = es.next_states[0] - es.cur_time
                        else:
                            pulse_width = 500.0e-6

                    else: # No more bits
                        break

                else: # Invalid pulse < 4us
                    break

            bit_starts.append(es.cur_time)
            return (frame_bits, bit_starts, pulse_width)

        # Get the frame bits
        frame_bits, bit_starts, pulse_width = collect_bits(es)
        if 34.0e-6 < pulse_width <= 43.0e-6 and es.cur_state() == 1:
            brk = J1850Break()
            sf = stream.StreamSegment((es.cur_time, es.next_states[0]), brk, kind='break')
            sf.annotate('frame', {'value':'Break'}, stream.AnnotationFormat.String)
            yield sf
            continue

        # Validate collected bits
        if len(frame_bits) % 8 != 0 or len(frame_bits) < 2 * 8:
            continue

        # Convert frame bits to bytes
        bytes = []
        for i in xrange(len(frame_bits) // 8):
            bytes.append(join_bits(frame_bits[i*8:i*8+8]))

        byte_starts = bit_starts[::8]

        header_len = 1 if bytes[0] & 0x10 else 3
        if header_len == 3 and len(bytes) < 4: continue


        priority = bytes[0] >> 5
        msg_type = bytes[0] & 0x0F
        data = bytes[header_len:-1]
        if len(data) == 0: data = None

        # Look for IFR
        if es.next_states[0] > es.cur_time:
            pulse_width = es.next_states[0] - es.cur_time
        else:
            pulse_width = 500.0e-6

        ifr_bytes = []
        ifr_byte_starts = []
        ifr_with_crc = False
        if 42.0e-6 <= pulse_width + (es.cur_time - bit_starts[-2]) <= 63.0e-6 and (msg_type & 0x08) == 0:
            # IFR is present
            es.advance_to_edge() # Start of first IFR bit

            ifr_with_crc = True if msg_type == J1850MT.FunctionRead else False

            # Get the IFR bits
            ifr_bits, ifr_bit_starts, pulse_width = collect_bits(es)
            if 34.0e-6 < pulse_width <= 43.0e-6 and es.cur_state() == 1:
                brk = J1850Break()
                sf = stream.StreamSegment((es.cur_time, es.next_states[0]), brk, kind='break')
                sf.annotate('frame', {'value':'Break'}, stream.AnnotationFormat.String)
                yield sf
                continue

            # Validate IFR bits
            if len(ifr_bits) % 8 == 0 and len(ifr_bits) >= 8:
                # Convert IFR bits to bytes
                for i in xrange(len(ifr_bits) // 8):
                    ifr_bytes.append(join_bits(ifr_bits[i*8:i*8+8]))

                ifr_byte_starts = ifr_bit_starts[::8]

        sf = _build_j1850_record(bytes, ifr_bytes, byte_starts, ifr_byte_starts, ifr_with_crc, \
                                (frame_start, es.cur_time + 4.0e-6))
        yield sf



def _build_j1850_record(bytes, ifr_bytes, byte_starts, ifr_byte_starts, ifr_with_crc, bounds):
    '''Create a J1850 frame from raw bytes'''
    header_len = 1 if bytes[0] & 0x10 else 3
    priority = bytes[0] >> 5
    msg_type = bytes[0] & 0x0F

    data = bytes[header_len:-1]
    if len(data) == 0: data = None

    ifr_data = None
    ifr_crc = None
    if len(ifr_bytes) > 0:
        ifr_data = ifr_bytes[:-1] if ifr_with_crc else ifr_bytes
        ifr_crc = ifr_bytes[-1] if ifr_with_crc else None

    if header_len == 3:
        nf = J1850Frame(priority, msg_type, data, bytes[1], bytes[2], crc=bytes[-1], \
                        ifr_data=ifr_data, ifr_crc=ifr_crc)
    else:
        nf = J1850Frame(priority, msg_type, data, crc=bytes[-1], ifr_data=ifr_data, ifr_crc=ifr_crc)

    sf = J1850StreamFrame(bounds, nf)

    # Add annotations

    bounds = (byte_starts[0], byte_starts[1])
    sf.subrecords.append(stream.StreamSegment(bounds, bytes[0], kind='header'))
    sf.subrecords[-1].annotate('ctrl', {'_bits':8})

    if header_len == 3:
        # Add target and source
        bounds = (byte_starts[1], byte_starts[2])
        sf.subrecords.append(stream.StreamSegment(bounds, bytes[1], kind='target'))
        sf.subrecords[-1].annotate('addr', {'_bits':8})

        bounds = (byte_starts[2], byte_starts[3])
        sf.subrecords.append(stream.StreamSegment(bounds, bytes[2], kind='source'))
        sf.subrecords[-1].annotate('addr', {'_bits':8})

    # Data
    for i, d in enumerate(bytes[header_len:-1]):
        bounds = (byte_starts[i+header_len], byte_starts[i+1+header_len])
        sf.subrecords.append(stream.StreamSegment(bounds, d, kind='data'))
        sf.subrecords[-1].annotate('data', {'_bits':8})

    # CRC
    bounds = (byte_starts[-2], byte_starts[-1])
    status = J1850StreamStatus.CRCError if not nf.crc_is_valid() else stream.StreamStatus.Ok
    sf.subrecords.append(stream.StreamSegment(bounds, bytes[-1], kind='CRC', status=status))
    sf.subrecords[-1].annotate('check', {'_bits':8})

    if len(ifr_bytes) > 0: # IFR
        last_ifr = len(ifr_bytes) if not ifr_with_crc else len(ifr_bytes) - 1
        for i, d in enumerate(ifr_bytes[:last_ifr]):
            bounds = (ifr_byte_starts[i], ifr_byte_starts[i+1])
            sf.subrecords.append(stream.StreamSegment(bounds, d, kind='IFR data'))
            sf.subrecords[-1].annotate('data', {'_bits':8})

        if ifr_with_crc:
            bounds = (ifr_byte_starts[-2], ifr_byte_starts[-1])
            status = J1850StreamStatus.CRCError if not nf.ifr_crc_is_valid() else stream.StreamStatus.Ok
            sf.subrecords.append(stream.StreamSegment(bounds, ifr_bytes[-1], kind='CRC', status=status))
            sf.subrecords[-1].annotate('check', {'_bits':8})


    return sf
            

def vpw_encode(bytes, start_time):
    '''Convert bytes to a VPW edge sequence

    bytes (sequence of int)
        The bytes to encode

    start_time (float)
        The Start time for the first edge

    Returns a list of (float, int) edge pairs.
    '''

    is_passive = 1
    edges = []
    t = start_time
    for byte in bytes:
        for b in split_bits(byte, 8):
            if is_passive:
                edges.append((t, 0))
                pw = 64.0e-6 if b == 0 else 128.0e-6
            else: # Active
                edges.append((t, 1))
                pw = 64.0e-6 if b == 1 else 128.0e-6

            t += pw
            is_passive = 1 - is_passive

    # Each frame has an even number of bits which guarantees the last bit
    # was in the active state. Thus there should be a falling edge at the
    # current time to end the last bit.
    edges.append((t, 0))

    return edges


def j1850_vpw_synth(frames, norm_bit=VPWNormBitStyle.SAE, breaks=None, idle_start=0.0, frame_interval=0.0, idle_end=0.0):
    '''Generate synthesized J1850 VPW data streams
    
    frames (sequence of J1850Frame or J1850Break)
        Frames to be synthesized.

    norm_bit (VPWNormBitStyle)
        How to interpret the normalization bit for In-Frame Response. Either standard SAE
        style or the GM specific variant. This determines whether the IFR is expected to
        have a CRC independently from the message type.

    breaks (sequence of (int, float))
        A set of tuples that identify which frames are interrupted by a break condition.
        The first int portion of the tuple identifies the frame index and the second float
        is the percentage (0.0 to 1.0) of the total frame that is generated before the break.

    idle_start (float)
        The amount of idle time before the transmission of frames begins.

    frame_interval (float)
        The amount of time between frames.

    idle_end (float)
        The amount of idle time after the last frame.

    Yields an edge stream of (float, int) pairs. The first element in the iterator
      is the initial state of the stream.
    '''

    t = 0.0

    yield (t, 0) # Initial conditions
    t += idle_start

    break_dict = {}
    if breaks is not None:
        break_dict = dict(breaks)

    for i, f in enumerate(frames):
        if isinstance(f, J1850Break):
            yield (t, 1)
            t += 400.0e-6
            yield (t, 0)
            t += 280.0e-6
            continue

        # SOF -> high for 200us
        yield (t, 1)
        t += 200.0e-6

        edges = vpw_encode(f.bytes, t)
        if i in break_dict:
            # Insert break into edge list for this frame
            brk_time = (edges[-1][0] - edges[0][0]) * break_dict[i] + edges[0][0]
            edges = [x for x in edges if x[0] <= brk_time] # Remove edges after the break
            t = edges[-1][0]
            if edges[-1][1] == 0: # Ensure last edge was 1
                edges = edges[:-1]
            t += 300.0e-6
            edges.append((t, 0))


        for e in edges: yield e
        t = edges[-1][0]

        include_ifr = True if f.ifr_data is not None and len(f.ifr_data) > 0 \
                                and (f.msg_type & 0x08) == 0 else False

        if include_ifr:
            t += 200.0e-6 # EOD symbol
        else: # No IFR
            t += 280.0e-6 # EOF symbol

        # If IFR is present it must start within the next 80us
        if include_ifr:
            if f.msg_type == J1850MT.FunctionRead:
                # Use type-3 IFR as indicated in J2178 5.2.1.5
                ifr_with_crc = True
            else:
                ifr_with_crc = False

            # Generate norm bit based on whether CRC is included
            t += 40.0e-6
            yield (t, 1)
            if norm_bit == VPWNormBitStyle.SAE: # Chrysler, et al.
                norm_pulse = 128.0e-6 if ifr_with_crc else 64.0e-6
            else: # GM: Standards? What standards?
                norm_pulse = 64.0e-6 if ifr_with_crc else 128.0e-6

            t += norm_pulse
            
            ifr_bytes = f.ifr_bytes if ifr_with_crc else f.ifr_data

            edges = vpw_encode(ifr_bytes, t)
            for e in edges: yield e
            t = edges[-1][0]

            t += 280.0e-6 # EOF symbol


        t += 100e-6 # IFS

        t += frame_interval

    t += idle_end
    yield (t, 0) # Final state



def single_to_diff(signal):
    '''Convert a single-ended edge stream to a differential pair

    signal (edge stream)
        The edges to convert to differential

    Returns a pair of edge streams p and m representing the + and - differential pair.
    '''
    p, m = itertools.izip(*_single_to_diff(signal))
    p = sigp.remove_excess_edges(p)
    m = sigp.remove_excess_edges(m)
    return p, m

def _single_to_diff(signal):
    for e in signal:
        yield (e, (e[0], 1 - e[1]))


def j1850_pwm_synth(frames, breaks=None, idle_start=0.0, frame_interval=0.0, idle_end=0.0):
    '''Generate synthesized J1850 PWM data streams
    
    frames (sequence of J1850Frame or J1850Break)
        Frames to be synthesized.

    breaks (sequence of (int, float))
        A set of tuples that identify which frames are interrupted by a break condition.
        The first int portion of the tuple identifies the frame index and the second float
        is the percentage (0.0 to 1.0) of the total frame that is generated before the break.

    idle_start (float)
        The amount of idle time before the transmission of frames begins.

    frame_interval (float)
        The amount of time between frames.

    idle_end (float)
        The amount of idle time after the last frame.

    Yields an edge stream of (float, int) pairs. The first element in the iterator
      is the initial state of the stream.
    '''
    return single_to_diff(_j1850_pwm_synth(frames, breaks, idle_start, frame_interval, idle_end))


def pwm_encode(bytes, start_time, bit_slice):
    '''Convert bytes to a PWM edge sequence

    bytes (sequence of int)
        The bytes to encode

    start_time (float)
        The Start time for the first edge

    bit_slice (float)
        The time for 1/3 of a bit period.

    Returns a list of (float, int) edge pairs.
    '''
    edges = []

    t = start_time
    for byte in bytes:
        for b in split_bits(byte, 8):
            edges.append((t, 1))
            pw = bit_slice if b == 1 else bit_slice * 2
            t += pw
            edges.append((t, 0))
            t += 3*bit_slice - pw

    edges.append((t, 0))
    return edges


def _j1850_pwm_synth(frames, breaks=None, idle_start=0.0, frame_interval=0.0, idle_end=0.0):
    '''Perform the actual PWM synthesis'''
    t = 0.0

    bit_rate = 41600

    bit_period = 1.0 / bit_rate
    bit_slice = bit_period / 3    

    yield (t, 0) # Initial conditions
    t += idle_start

    break_dict = {}
    if breaks is not None:
        break_dict = dict(breaks)

    for i, f in enumerate(frames):
        if isinstance(f, J1850Break):
            yield (t, 1)
            t += 5 * bit_slice
            yield (t, 0)
            t += 10 * bit_slice
            continue


        # SOF -> high for 4 slices, low for 2
        yield (t, 1)
        t += 4 * bit_slice
        yield (t, 0)
        t += 2 * bit_slice

        edges = pwm_encode(f.bytes, t, bit_slice)
        if i in break_dict:
            # Insert break into edge list for this frame
            brk_time = (edges[-1][0] - edges[0][0]) * break_dict[i] + edges[0][0]
            edges = [x for x in edges if x[0] <= brk_time] # Remove edges after the break
            t = edges[-1][0]
            if edges[-1][1] == 0: # Ensure last edge was 1
                edges = edges[:-1]
            t += 5 * bit_slice
            edges.append((t, 0))
            t += 10 * bit_slice
            edges.append((t, 0))

        for e in edges[:-1]: yield e
        t = edges[-1][0]

        include_ifr = True if f.ifr_data is not None and len(f.ifr_data) > 0 \
                                and (f.msg_type & 0x08) == 0 else False

        if include_ifr:
            t += bit_period # EOD
        else: # No IFR
            t += 2 * bit_period # EOF

        # If IFR is present is must start within the next bit period
        if include_ifr:
            if f.msg_type == J1850MT.FunctionRead:
                # Use type-3 IFR as indicated in J2178 5.2.1.5
                ifr_with_crc = True
            else:
                ifr_with_crc = False

            t += bit_period / 2

            ifr_bytes = f.ifr_bytes if ifr_with_crc else f.ifr_data

            edges = pwm_encode(ifr_bytes, t, bit_slice)
            for e in edges[:-1]: yield e
            t = edges[-1][0]

            t += 2 * bit_period # EOF

        t += bit_period # IFS

        t += frame_interval

    t += idle_end
    yield (t, 0) # Final state




# J1850 CRC params:
#         poly: 1d
#       xor in: ff
#      xor out: ff
#   reflect in: false
#  reflect out: false

def _crc8_table_gen():
    poly = 0x1d
    mask = 0xff

    tbl = [0] * 256

    for i in xrange(len(tbl)):
        sreg = i

        for j in xrange(8):
            if sreg & 0x80 != 0:
                sreg = (sreg << 1) ^ poly
            else:
                sreg <<= 1

        tbl[i] = sreg & mask

    return tbl


_crc8_table = _crc8_table_gen()


def table_j1850_crc8(d):
    '''Calculate J1850 CRC-8 on data
    
    This is a table-based byte-wise implementation
    
    d (sequence of int)
        Array of integers representing bytes
        
    Returns an integer with the CRC value.
    '''

    sreg = 0xff
    mask = 0xff

    tbl = _crc8_table

    for byte in d:
        tidx = (sreg ^ byte) & 0xff
        sreg = ((sreg << 8) ^ tbl[tidx]) & mask

    return sreg ^ mask


