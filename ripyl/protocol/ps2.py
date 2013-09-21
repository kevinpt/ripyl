#!/usr/bin/python
# -*- coding: utf-8 -*-

'''PS/2 and AT keyboard protocol decoder
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

import ripyl.streaming as stream
from ripyl.util.enum import Enum
from ripyl.decode import *
from ripyl.util.bitops import *
from ripyl.sigproc import remove_excess_edges

class PS2StreamStatus(Enum):
    '''Enumeration of PS/2 status codes'''
    FramingError = stream.StreamStatus.Error + 1
    ParityError = stream.StreamStatus.Error + 2
    AckError = stream.StreamStatus.Error + 3
    TimingError = stream.StreamStatus.Error + 4


class PS2Dir(Enum):
    '''Enumeration for PS/2 frame direction'''
    DeviceToHost = 0
    HostToDevice = 1


class PS2Frame(object):
    '''Frame object for PS/2 data'''
    def __init__(self, data, direction=PS2Dir.DeviceToHost):
        self.data = data
        self.direction = direction

    def __str__(self):
        return chr(self.data & 0xFF)

    def __eq__(self, other):
        return vars(self) == vars(other)

    def __ne__(self, other):
        return not (self == other)


class PS2StreamFrame(stream.StreamSegment):
    '''Streaming frame object for PS/2 data'''
    def __init__(self, bounds, frame, status=stream.StreamStatus.Ok):
        stream.StreamSegment.__init__(self, bounds, frame, status=status)
        self.kind = 'PS/2 frame'

    @classmethod
    def status_text(cls, status):
        if status >= PS2StreamStatus.FramingError and \
            status <= PS2StreamStatus.ParityError:
            
            return PS2StreamStatus(status)
        else:
            return stream.StreamSegment.status_text(status)

    def __str__(self):
        return str(self.data)



def ps2_decode(clk, data, logic_levels=None, stream_type=stream.StreamType.Samples):
    '''Decode a PS/2 data stream
    
    This is a generator function that can be used in a pipeline of waveform
    processing operations.
    
    Sample streams are a sequence of SampleChunk Objects. Edge streams are a sequence
    of 2-tuples of (time, int) pairs. The type of stream is identified by the stream_type
    parameter. Sample streams will be analyzed to find edge transitions representing
    0 and 1 logic states of the waveforms. With sample streams, an initial block of data
    on the clk stream is consumed to determine the most likely logic levels in the signal.
    
    clk (iterable of SampleChunk objects or (float, int) pairs)
        A sample stream or edge stream representing a PS/2 clk signal
    
    data (iterable of SampleChunk objects or (float, int) pairs)
        A sample stream or edge stream representing a PS/2 data signal.
    
    logic_levels ((float, float) or None)
        Optional pair that indicates (low, high) logic levels of the sample
        stream. When present, auto level detection is disabled. This has no effect on
        edge streams.

    stream_type (streaming.StreamType)
        A StreamType value indicating that the clk and data parameters represent either Samples
        or Edges

    Yields a series of PS2StreamFrame objects.
      
    Raises AutoLevelError if stream_type = Samples and the logic levels cannot
      be determined.
    '''

    if stream_type == stream.StreamType.Samples:
        if logic_levels is None:
            s_clk_it, logic_levels = check_logic_levels(clk)
        else:
            s_clk_it = clk
        
        hyst = 0.4
        clk_it = find_edges(s_clk_it, logic_levels, hysteresis=hyst)
        data_it = find_edges(data, logic_levels, hysteresis=hyst)

    else: # the streams are already lists of edges
        clk_it = clk
        data_it = data

    edge_sets = {
        'clk': clk_it,
        'data': data_it
    }
    
    es = MultiEdgeSequence(edge_sets, 0.0)

    # begin to decode

    direction = PS2Dir.DeviceToHost
    find_frame_start = True
    bits_remaining = 10
    bits = []
    byte_complete = False


    # Minimum clock is 10kHz
    min_period = 1.0 / 10.0e3 * 1.05 # add 5%


    while not es.at_end('clk'):
        ts, cname = es.advance_to_edge(channel_name='clk')

        if es.at_end('clk'):
            continue

        clk_val = es.cur_state('clk')
        d_val = es.cur_state('data')

        if ts > 100.0e-6 and not find_frame_start:
            # Some sort of framing error happened. Start over to resynchronize
            find_frame_start = True
            bits = []
            ne = stream.StreamEvent(es.cur_time(), kind='PS/2 resynch', \
                status=PS2StreamStatus.FramingError)
            yield ne
            

        if find_frame_start == True and (d_val == 0):
            bits_remaining = 10
            start_time = es.cur_time()
            timing_error = False
            if clk_val == 0: # falling edge
                direction = PS2Dir.DeviceToHost
                find_frame_start = False
            elif clk_val == 1 and ts > 100.0e-6:
                direction = PS2Dir.HostToDevice
                find_frame_start = False
                get_ack = False
            continue


        if not find_frame_start:
            # Confirm that the clock rate is fast enough
            # We should always be advancing by no more than 1/2 the minimum clock period
            if ts > (min_period / 2):
                timing_error = True

            if direction == PS2Dir.DeviceToHost:
                if clk_val == 0: # this is a falling edge, capture data
                    if bits_remaining:
                        bits.append(d_val)
                        bits_remaining -= 1

                    if not bits_remaining: # completed a byte, verify and build frame object
                        end_time = es.cur_time()
                        bit_period = (end_time - start_time) / 10
                        start_time -= bit_period / 2
                        end_time += bit_period / 2

                        data_time = start_time + bit_period
                        parity_time = end_time - (bit_period * 2)
                        stop_time = end_time - bit_period
                        stop_end_time = end_time

                        byte_complete = True

            else: # HostToDevice
                if clk_val == 1 and get_ack == False: # this is a rising edge, capture data
                    if bits_remaining:
                        bits.append(d_val)
                        bits_remaining -= 1

                    if not bits_remaining: # ready to look for ack
                        get_ack = True

                elif clk_val == 0 and get_ack == True:
                    bits.append(d_val)

                    end_time = es.cur_time()
                    bit_period = (end_time - start_time) / 10.5
                    start_time -= bit_period / 2
                    end_time += bit_period / 2

                    data_time = start_time + bit_period
                    parity_time = end_time - (bit_period * 2.5)
                    stop_time = end_time - (bit_period * 1.5)
                    ack_time = end_time - (bit_period * 0.75)
                    stop_end_time = ack_time

                    byte_complete = True
                    if d_val == 0:
                        es.advance_to_edge('data') # move ahead to rising edge of ack pulse

            if byte_complete:

                data = join_bits(reversed(bits[0:8]))
                p = 1
                for b in bits[0:8]:
                    p ^= b

                parity_error = True if p != bits[8] else False
                
                framing_error = True if bits[9] != 1 else False # missing stop bit


                status = PS2StreamStatus.FramingError if framing_error else \
                    PS2StreamStatus.TimingError if timing_error else stream.StreamStatus.Ok

                nf = PS2StreamFrame((start_time, end_time), PS2Frame(data, direction), status=status)
                nf.annotate('frame', {}, stream.AnnotationFormat.Hidden)

                nf.subrecords.append(stream.StreamSegment((start_time, data_time), kind='start bit'))
                nf.subrecords[-1].annotate('misc', {'_bits':1}, stream.AnnotationFormat.Invisible)
                nf.subrecords.append(stream.StreamSegment((data_time, parity_time), data, kind='data bits'))
                nf.subrecords[-1].annotate('data', {'_bits':bits}, stream.AnnotationFormat.General)

                status = PS2StreamStatus.ParityError if parity_error else stream.StreamStatus.Ok
                nf.subrecords.append(stream.StreamSegment((parity_time, stop_time), kind='parity', status=status))
                nf.subrecords[-1].annotate('check', {'_bits':1}, stream.AnnotationFormat.Hidden)
                nf.subrecords.append(stream.StreamSegment((stop_time, stop_end_time), kind='stop bit'))
                nf.subrecords[-1].annotate('misc', {'_bits':1}, stream.AnnotationFormat.Invisible)

                if direction == PS2Dir.HostToDevice:
                    ack_error = True if bits[10] != 0 else False
                    status = PS2StreamStatus.AckError if ack_error else stream.StreamStatus.Ok
                    nf.subrecords.append(stream.StreamSegment((ack_time, end_time), kind='ack bit', status=status))
                    nf.subrecords[-1].annotate('ack', {'_bits':1}, stream.AnnotationFormat.Hidden)

                bits = []
                find_frame_start = True
                byte_complete = False

                yield nf


                        


def ps2_synth(frames, clock_freq, idle_start=0.0, word_interval=0.0):
    '''Generate synthesized PS/2 waveform
    
    This function simulates a transmission of data over PS/2.
    
    This is a generator function that can be used in a pipeline of waveform
    procesing operations.

    frames (sequence of PS2Frame)
        A sequence of PS2Frame objects that will be transmitted serially

    clock_freq (float)
        The PS/2 clock frequency. 10kHz - 13KHz typ.
    
    idle_start (float)
        The amount of idle time before the transmission of data begins
    
    word_interval (float)
        The amount of time between data bytes

    Yields a set of pairs representing the two edge streams for clk and data
      respectively. Each edge stream pair is in (time, value) format representing the
      time and logic value (0 or 1) for each edge transition. The first set of pairs
      yielded is the initial state of the waveforms.
    '''

    # This is a wrapper around the actual synthesis code in _ps2_synth()
    # It unzips the yielded tuple and removes unwanted artifact edges
    clk, data = itertools.izip(*_ps2_synth(frames, clock_freq, idle_start, word_interval))
    clk = remove_excess_edges(clk)
    data = remove_excess_edges(data)
    return clk, data

def _ps2_synth(frames, clock_freq, idle_start=0.0, word_interval=0.0):
    '''Core PS/2 synthesizer
    
    This is a generator function.
    '''

    t = 0.0
    word_size = 11 # 8-data + start + stop + parity

    clk = 1
    data = 1
    
    half_bit_period = 1.0 / (2.0 * clock_freq)

    
    yield ((t, clk),(t, data)) # initial conditions
    t += idle_start
     
    #for d, direct in zip(frames, direction):
    for frame in frames:
        d = frame.data
        direct = frame.direction
        bits_remaining = word_size

        # first bit transmitted will be at the end of the list
        bits = split_bits(d, 8)

        # add start, stop, and parity bits (in reverse order)
        p = 1 # odd parity
        for b in bits:
            p ^= b

        bits = [1, p] + bits + [0]

        if direct == PS2Dir.DeviceToHost:
            while bits_remaining:
                data = bits[bits_remaining-1]
                bits_remaining -= 1
                yield ((t, clk),(t, data))
                t += half_bit_period
                clk = 1 - clk
                yield ((t, clk),(t, data))
                t += half_bit_period
                clk = 1 - clk

            yield ((t, clk),(t, data))


        else: # HostToDevice
            # Generate RTS from host
            clk = 0
            yield ((t, clk),(t, data))

            t += 110.0e-6 # hold clock low for 110us

            while bits_remaining > 1:
                data = bits[bits_remaining-1]
                bits_remaining -= 1
                yield ((t, clk),(t, data))
                t += half_bit_period
                clk = 1 - clk
                yield ((t, clk),(t, data))
                t += half_bit_period
                clk = 1 - clk

            # The stop bit is driven for .75 cycles before the ack arrives
            data = bits[bits_remaining-1]
            bits_remaining -= 1
            yield ((t, clk),(t, data))
            t += half_bit_period
            clk = 1 - clk
            yield ((t, clk),(t, data))
            t += half_bit_period / 2


            # Generate ack pulse
            data = 0
            yield ((t, clk),(t, data))

            t += half_bit_period / 2
            clk = 1 - clk
            yield ((t, clk),(t, data))

            t += half_bit_period
            clk = 1 - clk
            data = 1
            yield ((t, clk),(t, data))

        t += word_interval
        
    t += half_bit_period
        
    yield ((t, clk),(t, data)) # final state


