#!/usr/bin/python
# -*- coding: utf-8 -*-

'''LIN protocol decoder
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

import operator

import ripyl
import ripyl.streaming as stream
import ripyl.sigproc as sigp
from ripyl.util.enum import Enum
from ripyl.util.bitops import split_bits, join_bits
import ripyl.protocol.uart as uart
from copy import copy


class LINChecksum(Enum):
    '''Enumeration for LIN checksum type'''
    Classic = 0
    Enhanced = 1


class LINFrame(object):
    '''LIN frame object'''
    def __init__(self, id, data=None, checksum=None, pid_parity=None, cs_type=LINChecksum.Classic):
        '''
        id (int)
            The ID field from the PID

        data (sequence of int or None)
            Optional sequence of data bytes for the frame. Should be between 1 and 8 bytes long.
            An empty list is converted to None.

        checksum (int or None)
            Optional checksum for the frame
        
        pid_parity (int or None)
            Optional parity bits from the PID field

        cs_type (LINChecksum)
            The checksum type to use for this frame

        '''

        if data is not None:
            if len(data) == 0:
                data = None
            else:
                data = data[:8]

        self.id = id
        self.data = data
        self._checksum = checksum
        self._pid_parity = pid_parity
        self.cs_type = cs_type

        #print('#### create frame:', self.id, self._checksum)

    def __repr__(self):
        return 'LINFrame({}, {}, {}, {}, {})'.format(self.id, self.data, self._checksum, self._pid_parity, self.cs_type)


    @property
    def pid(self):
        '''Get the frame PID'''
        return (self.pid_parity << 6) + self.id

    @property
    def pid_parity(self):
        '''The parity bits from the PID'''
        if self._pid_parity is None:
            return lin_pid(self.id) >> 6
        else:
            return self._pid_parity

    @pid_parity.setter
    def pid_parity(self, value):
        self._pid_parity = value


    @property
    def checksum(self):
        '''The frame checksum'''
        if self._checksum is None:
            return self.data_checksum
        else:
            return self._checksum

    @checksum.setter
    def checksum(self, value):
        self._checksum = value


    @property
    def data_checksum(self):
        '''Get the checksum over the data bytes without reference to any existing _checksum value'''
        if self.data is None:
            raise ValueError('No data in frame')

        # Identifiers 60 and 61 are always protected with LIN 1.3 checksums
        if self.cs_type == LINChecksum.Classic or (self.id in (60, 61)):
            return lin_checksum(self.data)

        else:
            return lin_checksum([self.pid] + self.data)



    def checksum_is_valid(self, recv_cs=None):
        '''Determine if the checksum is valid

        recv_cs (int or None)
            Optional received checksum value. If None, the stored checksum
            for the frame is used instead.

        '''
        if recv_cs is None:
            recv_cs = self._checksum

        data_cs = self.data_checksum
        
        return recv_cs == data_cs


    def pid_is_valid(self):
        '''Determine if the PID parity bits are correct'''
        return self.pid_parity == (lin_pid(self.id) >> 6)

    def bytes(self):
        '''Returns a sequence of raw frame bytes including the sync field'''
        if self.data is None or len(self.data) == 0:
            return [0x55, self.pid]
        else:
            return [0x55, self.pid] + self.data + [self.checksum]

    def __eq__(self, other):
        s_vars = copy(vars(self))
        o_vars = copy(vars(other))


        s_vars['_pid_parity'] = self.pid_parity
        o_vars['_pid_parity'] = other.pid_parity

        if self._checksum is not None:
            s_vars['_checksum'] = self.checksum
            o_vars['_checksum'] = other.checksum

        #print('### sv:', s_vars)
        #print('### ov:', o_vars)
        if self.data is None:
            # The checksum type is irrelevant since this is just a header
            del s_vars['cs_type']
            del o_vars['cs_type']

        return s_vars == o_vars

    def __ne__(self, other):
        return not (self == other)


class LINStreamStatus(Enum):
    '''Enumeration for LINStreamFrame status codes'''
    PIDError      = stream.StreamStatus.Error + 1
    ChecksumError = stream.StreamStatus.Error + 2        


class LINStreamFrame(stream.StreamSegment):
    '''Encapsulates a LINFrame object into a StreamSegment'''
    def __init__(self, bounds, frame, status=stream.StreamStatus.Ok):
        stream.StreamSegment.__init__(self, bounds, data=frame, status=status)
        self.kind = 'LIN frame'

        self.annotate('frame', {}, stream.AnnotationFormat.Hidden)


def lin_checksum(data):
    '''Compute the LIN checksum

    data (sequence of int)
        The bytes (including ID if enhanced format) to compute the checksum over

    Returns the checksum as an int.
    '''
    cs = 0
    for d in data:
        cs += d
        if cs >= 256: # Wraparound the carry bit
            cs -= 255

    return cs ^ 0xFF # Invert result



_p0_mask = 0x17 # ID 0, 1, 2, 4
_p1_mask = 0x3A # ID 1, 3, 4, 5

def lin_pid(id):
    '''Generate a LIN PID from an ID

    id (int)
        The ID to generate parity for

    Returns the PID as an int.
    '''

    p0 = reduce(operator.xor, split_bits(id & _p0_mask, 6))
    p1 = reduce(operator.xor, split_bits(id & _p1_mask, 6)) ^ 0x01

    return join_bits([p1, p0] + split_bits(id, 6))


def lin_decode(stream_data, enhanced_ids=None, baud_rate=None, logic_levels=None,\
                stream_type=stream.StreamType.Samples, param_info=None):
    '''Decode a LIN data stream

    This is a generator function that can be used in a pipeline of waveform
    procesing operations.

    Sample streams are a sequence of SampleChunk Objects. Edge streams are a sequence
    of 2-tuples of (time, int) pairs. The type of stream is identified by the stream_type
    parameter. Sample streams will be analyzed to find edge transitions representing
    0 and 1 logic states of the waveforms. With sample streams, an initial block of data
    is consumed to determine the most likely logic levels in the signal.

    stream_data (iterable of SampleChunk objects or (float, int) pairs)
        A sample stream or edge stream representing a LIN signal.

    enhanced_ids (sequence of int or None)
        An optional sequence of frame IDs that are to use LIN 2.x enhanced checksums.
        If None, the checksum type is guessed by trying both methods to see if one matches
        decoded checksum.

    baud_rate (int or None)
        The baud rate of the stream. If None, the first 50 edges will be analyzed to
        automatically determine the most likely baud rate for the stream. On average
        50 edges will occur after 11 bytes have been captured.

    logic_levels ((float, float) or None)
        Optional pair that indicates (low, high) logic levels of the sample
        stream. When present, auto level detection is disabled. This has no effect on
        edge streams.
    
    stream_type (streaming.StreamType)
        A StreamType value indicating that the stream parameter represents either Samples
        or Edges

    param_info (dict or None)
        An optional dictionary object that is used to monitor the results of
        automatic baud detection.
        
        
    Yields a series of LINStreamFrame objects.
      
    Raises AutoLevelError if stream_type = Samples and the logic levels cannot
      be determined.
      
    Raises AutoBaudError if auto-baud is active and the baud rate cannot
      be determined.
    '''
    if stream_type == stream.StreamType.Samples:
        if logic_levels is None:
            samp_it, logic_levels = ripyl.decode.check_logic_levels(stream_data)
        else:
            samp_it = stream_data
        
        edges = ripyl.decode.find_edges(samp_it, logic_levels, hysteresis=0.4)
    else: # the stream is already a list of edges
        edges = stream_data

    bits = 8
    parity = None
    stop_bits = 1
    polarity = uart.UARTConfig.IdleHigh

    records_it = uart.uart_decode(edges, bits, parity, stop_bits, lsb_first=True, \
        polarity=polarity, baud_rate=baud_rate, use_std_baud=False, logic_levels=logic_levels, \
        stream_type=stream.StreamType.Edges, param_info=param_info)

    S_NEED_BREAK = 0
    S_SYNC = 1
    S_DATA = 2

    state = S_NEED_BREAK
    raw_bytes = []
    frame_start = 0.0
    next_frame_start = 0.0
    frame_complete = False
    for r in records_it:
        # Look for a break condition
        if state == S_NEED_BREAK:
            if r.data == 0 and r.status == uart.UARTStreamStatus.FramingError:
                frame_start = r.start_time
                state = S_SYNC

        elif state == S_SYNC:
            if r.data == 0x55:
                raw_bytes = []
                state = S_DATA
            else:
                state = S_NEED_BREAK

        elif state == S_DATA:
            # Collect frame bytes until we see another break or we have 10 bytes (1 pid + 8 data + 1 checksum)
            if r.data == 0 and r.status == uart.UARTStreamStatus.FramingError:
                next_frame_start = r.start_time
                frame_complete = True
                state = S_SYNC

            else:
                raw_bytes.append(r)

            if len(raw_bytes) >= 10:
                frame_complete = True
                state = S_NEED_BREAK


        if frame_complete:
            sf = _make_lin_frame(raw_bytes, frame_start, enhanced_ids)
            frame_complete = False
            frame_start = next_frame_start
            raw_bytes = []

            yield sf

    if len(raw_bytes) > 0: # Partial frame remains
        sf = _make_lin_frame(raw_bytes, frame_start, enhanced_ids)
        yield sf

        

def _make_lin_frame(raw_bytes, frame_start, enhanced_ids):
    '''Generate a LINStreamFrame from raw bytes'''
    if len(raw_bytes) >= 2:
        lf = LINFrame(raw_bytes[0].data & 0x3F, [b.data for b in raw_bytes[1:-1]],\
                raw_bytes[-1].data, pid_parity=raw_bytes[0].data >> 6)
    else:
        lf = LINFrame(raw_bytes[0].data & 0x3F, pid_parity=raw_bytes[0].data >> 6)

    if lf.data is not None:
        if enhanced_ids is not None:
            if lf.id in enhanced_ids:
                lf.cs_type = LINChecksum.Enhanced
        else: # Determine checksum type automatically
            if not lf.checksum_is_valid():
                lf.cs_type = LINChecksum.Enhanced # Try using enhanced checksum
                if not lf.checksum_is_valid():
                    lf.cs_type = LINChecksum.Classic # Revert to classic checksum

    sf = LINStreamFrame((frame_start, raw_bytes[-1].end_time), lf)

    # Add annotated PID field
    pid_start = raw_bytes[0].subrecords[1].start_time
    pid_end = raw_bytes[0].subrecords[1].end_time
    id_end = (pid_end - pid_start) / 8 * 6 + pid_start

    sf.subrecords.append(stream.StreamSegment((pid_start, id_end), lf.id, kind='ID'))
    sf.subrecords[-1].annotate('addr', {'_bits':6})

    status = stream.StreamStatus.Ok if lf.pid_is_valid() else LINStreamStatus.PIDError
    sf.subrecords.append(stream.StreamSegment((id_end, pid_end), lf.pid >> 6, kind='PID parity', status=status))
    sf.subrecords[-1].annotate('check', {'_bits':2}, stream.AnnotationFormat.Hidden)


    if len(raw_bytes) >= 2:
        if len(raw_bytes) > 2: # Add data annotation
            for d in raw_bytes[1:-1]:
                d_info = d.subrecords[1]
                sf.subrecords.append(stream.StreamSegment((d_info.start_time, d_info.end_time), d.data, kind='data'))
                sf.subrecords[-1].annotate('data', {'_bits':8})

        # Add checksum annotation
        cs_info = raw_bytes[-1].subrecords[1]
        status = stream.StreamStatus.Ok if lf.checksum_is_valid() else LINStreamStatus.ChecksumError
        sf.subrecords.append(stream.StreamSegment((cs_info.start_time, cs_info.end_time),\
                            lf.checksum, kind='checksum', status=status))
        sf.subrecords[-1].annotate('check', {'_bits':8}, stream.AnnotationFormat.Hex)


    return sf



def lin_synth(frames, baud, idle_start=0.0, frame_interval=8.0e-3, idle_end=0.0, byte_interval=1.0e-3):
    '''Generate synthesized LIN data streams
    
    frames (sequence of LINFrame)
        Frames to be synthesized.

    baud (int)
        The baud rate.

    idle_start (float)
        The amount of idle time before the transmission of messages begins.

    frame_interval (float)
        The amount of time between frames.
    
    idle_end (float)
        The amount of idle time after the last message.

    byte_interval (float)
        The amount of time between message bytes.

    Yields an edge stream of (float, int) pairs. The first element in the iterator
      is the initial state of the stream.
    '''

    return sigp.remove_excess_edges(_lin_synth(frames, baud, idle_start, frame_interval, idle_end, byte_interval))

def _lin_synth(frames, baud, idle_start=0.0, frame_interval=8.0e-3, idle_end=0.0, byte_interval=1.0e-3):
    '''The LIN core synthesizer'''

    bit_period = 1.0 / baud

    frame_its = []
    for i, f in enumerate(frames):
        iend = idle_end if i == len(frames)-1 else 0.0

        # Generate the break character starting the frame
        if i == 0 and idle_start > 0.0:
            break_edges = [(0.0, 1), (idle_start, 0), (idle_start + 14.0 * bit_period, 1)]
        else:
            break_edges = [(0.0, 0), (14.0 * bit_period, 1)]
        
        # Generate bytes for the rest of the frame
        byte_edges = uart.uart_synth(f.bytes(), bits=8, baud=baud, idle_start=0.0, \
                    idle_end=iend, word_interval=byte_interval)

        frame_its.append(sigp.chain_edges(bit_period, break_edges, byte_edges))

    return sigp.chain_edges(frame_interval, *frame_its)

