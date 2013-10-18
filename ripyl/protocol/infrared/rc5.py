#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Philips RC-5 IR protocol decoder
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

import ripyl.decode as decode
import ripyl.streaming as stream
from ripyl.util.bitops import split_bits, join_bits

import ripyl.protocol.infrared as ir


class RC5Message(object):
    '''RC-5 infrared message'''
    def __init__(self, cmd, addr, toggle):
        self.cmd = cmd
        self.addr = addr
        self.toggle = toggle

    def __repr__(self):
        return 'RC5Message({}, {}, {})'.format(self.cmd, self.addr, self.toggle)

    def __eq__(self, other):
        return vars(self) == vars(other)

    def __ne__(self, other):
        return not (self == other)


class RC5StreamMessage(stream.StreamSegment):
    '''Message object for RC-5 data'''
    def __init__(self, bounds, data=None, status=stream.StreamStatus.Ok):
        stream.StreamSegment.__init__(self, bounds, data, status=status)
        self.kind = 'RC-5 message'


def rc5_decode(ir_stream, carrier_freq=36.0e3, polarity=ir.IRConfig.IdleLow, logic_levels=None, \
     stream_type=stream.StreamType.Samples):

    '''Decode RC5 infrared protocol

    This is a generator function that can be used in a pipeline of waveform
    procesing operations.
    
    ir_stream (iterable of SampleChunk objects or (float, int) pairs)
        A sample stream or edge stream of IR pulses. The type of stream is identified
        by the stream_type parameter. When this is a sample stream, an initial block
        of data is consumed to determine the most likely logic levels in the signal.
        This signal can be either modulated or demodulated.

    carrier_freq (float)
        The carrier frequency for modulation.

    polarity (infrared.IRConfig)
        Set the polarity (idle state high or low).
    
    logic_levels ((float, float) or None)
        Optional pair that indicates (low, high) logic levels of the sample
        stream. When present, auto level detection is disabled. This has no effect on
        edge streams.
    
    stream_type (streaming.StreamType)
        A StreamType value indicating that the ir_stream parameter represents either Samples
        or Edges.
        
    Yields a series of RC5StreamMessage objects.
      
    Raises AutoLevelError if stream_type = Samples and the logic levels cannot
      be determined.
    '''

    if stream_type == stream.StreamType.Samples:
        if logic_levels is None:
            samp_it, logic_levels = decode.check_logic_levels(ir_stream)
        else:
            samp_it = ir_stream
        
        edges = decode.find_edges(samp_it, logic_levels, hysteresis=0.4)
    else: # the stream is already a list of edges
        edges = ir_stream

    # Demodulate signal (also passes an unmodulated signal without changes)
    edges = ir.demodulate(edges, carrier_freq, polarity)

    pulse_width = 889.0e-6 # 889us pulse width
    es = decode.EdgeSequence(edges, pulse_width)

    while not es.at_end():
        # Look for the rising edge of a pulse
        if es.cur_state() == 0:
            es.advance_to_edge() # Now we're 1
        msg_start_time = es.cur_time - pulse_width

        # Move ahead half a pulse and check that we are still 1
        es.advance(pulse_width / 2.0)
        if es.cur_state() != 1:
            continue

        # Advance through edge sequence recording state until we see 3 0's or 3 1's in a row
        # This indicates a break in the Manchester encoding.

        coded_bits = [0, 1]
        bit_starts = [0.0, 0.0]
        same_count = 1
        prev_state = 1
        while True:
            es.advance()
            coded_bits.append(es.cur_state())
            bit_starts.append(es.cur_time - pulse_width / 2.0)
            if es.cur_state() == prev_state:
                same_count += 1
            else:
                same_count = 1

            if same_count > 2:
                break

            prev_state = es.cur_state()

        msg_end_time = es.cur_time - pulse_width

        if len(coded_bits) >= 14 * 2:
            # Decode Manchester
            # The second bit of each pair is the same as the decoded bit
            msg_bits = coded_bits[1:28:2]
            mb_starts = bit_starts[::2]

            #print('$$$ coded_bits:', coded_bits)
            #print('$$$ msg_bits:', msg_bits)

            toggle = msg_bits[2]
            addr = join_bits(msg_bits[3:8])
            cmd = join_bits([0 if msg_bits[1] else 1] + msg_bits[8:14])
            msg = RC5Message(cmd, addr, toggle)
            sm = RC5StreamMessage((msg_start_time, msg_end_time), msg)
            sm.annotate('frame', {'name':'frame'}, stream.AnnotationFormat.Hidden)

            sm.subrecords.append(stream.StreamSegment((mb_starts[2], mb_starts[3]), toggle, kind='toggle'))
            sm.subrecords[-1].annotate('data', {'_bits':1}, stream.AnnotationFormat.Int)
            sm.subrecords.append(stream.StreamSegment((mb_starts[3], mb_starts[8]), addr, kind='addr'))
            sm.subrecords[-1].annotate('addr', {'_bits':5})
            sm.subrecords.append(stream.StreamSegment((mb_starts[8], mb_starts[14]), cmd, kind='cmd'))
            sm.subrecords[-1].annotate('data', {'_bits':6})
            if cmd > 63:
                # Extended format; 7-th bit is just after first start bit
                sm.subrecords[-1].fields['_bits'] = 7
                sm.subrecords.append(stream.StreamSegment((mb_starts[1], mb_starts[2]), msg_bits[1], kind='cmd bit-7'))
                sm.subrecords[-1].annotate('data1', {'_bits':1}, stream.AnnotationFormat.Int)

            yield sm


def rc5_synth(messages, idle_start=0.0, message_interval=89.0e-3, idle_end=1.0e-3):
    '''Generate synthesized RC5 infrared waveforms
    
    This function simulates Philips RC5 IR pulses.

    messages (sequence of RC5Message)
        Commands to be synthesized.
    
    idle_start (float)
        The amount of idle time before the transmission of messages begins.

    message_interval (float)
        The amount of time between messages.
    
    idle_end (float)
        The amount of idle time after the last message.

    Yields an edge stream of (float, int) pairs. The first element in the iterator
      is the initial state of the stream.
    '''

    t = 0.0

    pulse_width = 889.0e-6 # 889us pulse width
    
    yield (t, 0) # set initial conditions; idle-low
    t += idle_start

    for msg in messages:
        msg_bits = [1, 0 if (msg.cmd & 0x40) else 1, msg.toggle]
        msg_bits.extend(split_bits(msg.addr, 5))
        msg_bits.extend(split_bits(msg.cmd, 6))

        #print('### msg_bits:', msg_bits)

        coded_bits = ((0, 1) if b else (1, 0) for b in msg_bits) # Expand each bit into a pair of half bits
        coded_bits = (b for sl in coded_bits for b in sl) # Flatten the tuples

        prev_state = 0
        for b in coded_bits:
            if b != prev_state:
                yield (t, b)
            t += pulse_width
            prev_state = b

        if prev_state == 1:
            yield (t, 0)

        t += message_interval
            
    t += idle_end - message_interval
        
    yield (t, 0) # Final state


