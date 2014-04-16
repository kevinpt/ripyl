#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Philips RC-6 IR protocol decoder

NOTE: There are no publicly available RC-6 documents describing the complete message format.
Only mode-0 and mode-6 (RC6A) is properly supported by this decoder.
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

import functools

import ripyl.decode as decode
import ripyl.streaming as stream
from ripyl.util.bitops import split_bits, join_bits

import ripyl.protocol.infrared as ir


# RC6  Mode-0 : start mode(3) toggle(1*) addr(8) cmd(8)
# RC6A Mode-6 : start mode(3) toggle(1*) size(1) customer(7 + size*8) addr(8) cmd(8)

class RC6Message(object):
    '''RC-6 infrared message'''
    def __init__(self, cmd, addr, toggle, mode=0, customer=None):
        self.toggle = toggle
        self.addr = addr
        self.cmd = cmd
        self.mode = mode
        self.customer = customer

    def __repr__(self):
        if self.customer is None:
            return 'RC6Message({}, {}, {}, {})'.format(self.cmd, self.addr, self.toggle, self.mode)
        else:
            return 'RC6Message({}, {}, {}, {}, {})'.format(self.cmd, self.addr, self.toggle, self.mode, self.customer)

    def __eq__(self, other):
        return vars(self) == vars(other)

    def __ne__(self, other):
        return not (self == other)


class RC6StreamMessage(stream.StreamSegment):
    '''Message object for RC-6 data'''
    def __init__(self, bounds, data=None, status=stream.StreamStatus.Ok):
        stream.StreamSegment.__init__(self, bounds, data, status=status)
        self.kind = 'RC-6 message'


def rc6_decode(ir_stream, carrier_freq=36.0e3, polarity=ir.IRConfig.IdleLow, logic_levels=None, \
     stream_type=stream.StreamType.Samples):

    '''Decode RC6 infrared protocol

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
        
    Yields a series of RC6StreamMessage objects.
      
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

    pulse_width = 444.0e-6 # 444us pulse width
    es = decode.EdgeSequence(edges, pulse_width)

    epsilon = 30.0e-6 # allow +/-30us variation for pulses and bit times
    time_is_nearly = functools.partial(ir.time_is_nearly, epsilon=epsilon)


    while not es.at_end():
        # Look for the rising edge of a pulse
        if es.cur_state() == 0:
            es.advance_to_edge() # Now we're 1
        msg_start_time = es.cur_time

        ts = es.advance_to_edge()
        if not time_is_nearly(ts, 6 * pulse_width):
            continue # This is not the leading AGC pulse of a message

        ts = es.advance_to_edge()
        if not time_is_nearly(ts, 2 * pulse_width):
            continue # This is not the leading AGC pulse of a message

        # Move ahead half a pulse and check that we are still 1
        es.advance(pulse_width / 2.0)
        if es.cur_state() != 1:
            continue # Not a valid start bit

        es.advance() # End of start bit

        # Advance through edge sequence recording state until we see 4 0's or 4 1's in a row
        # This indicates a break in the Manchester encoding.

        coded_bits = [1, 0] # Start bit
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

            if same_count > 3:
                break

            prev_state = es.cur_state()

        msg_end_time = es.cur_time - 2.5 * pulse_width

        #print('$$$ found bits:', len(coded_bits))

        if len(coded_bits) >= 22 * 2:
            # Decode Manchester
            # The first bit of each pair is the same as the decoded bit
            msg_bits = coded_bits[0:44:2]
            mb_starts = bit_starts[::2]

            mode = join_bits(msg_bits[1:4])
            toggle = msg_bits[4]

            if mode == 6: # RC6A message
                if msg_bits[6]: # 15-bit customer field
                    msg_bits = coded_bits[0:76:2]
                    customer = join_bits(msg_bits[7:22])
                    asb = 22 # addr start bit index
                else: # 7-bit customer field
                    msg_bits = coded_bits[0:60:2]
                    customer = join_bits(msg_bits[7:14])
                    asb = 14
            else: # RC6 message
                customer = None
                asb = 6

            #print('$$$ coded_bits:', coded_bits)
            #print('$$$       msg_bits:', msg_bits)


            addr = join_bits(msg_bits[asb:asb+8])
            cmd = join_bits(msg_bits[asb+8:asb+16])
            msg = RC6Message(cmd, addr, toggle, mode, customer)
            sm = RC6StreamMessage((msg_start_time, msg_end_time), msg)
            sm.annotate('frame', {'name':'frame'}, stream.AnnotationFormat.Hidden)

            sm.subrecords.append(stream.StreamSegment((mb_starts[1], mb_starts[4]), mode, kind='mode'))
            sm.subrecords[-1].annotate('addr', {'_bits':3})
            sm.subrecords.append(stream.StreamSegment((mb_starts[4], mb_starts[6]), toggle, kind='toggle'))
            sm.subrecords[-1].annotate('data', {'_bits':1}, stream.AnnotationFormat.Int)
           
            if mode == 6:
                sm.subrecords.append(stream.StreamSegment((mb_starts[6], mb_starts[asb]), customer, kind='customer'))
                sm.subrecords[-1].annotate('data', {'_bits':7 + msg_bits[6]*8})

            sm.subrecords.append(stream.StreamSegment((mb_starts[asb], mb_starts[asb+8]), addr, kind='addr'))
            sm.subrecords[-1].annotate('addr', {'_bits':8})
            sm.subrecords.append(stream.StreamSegment((mb_starts[asb+8], mb_starts[asb+16]), cmd, kind='cmd'))
            sm.subrecords[-1].annotate('data', {'_bits':8})


            yield sm


def rc6_synth(messages, idle_start=0.0, message_interval=89.0e-3, idle_end=1.0e-3):
    '''Generate synthesized RC6 infrared waveforms
    
    This function simulates Philips RC6 IR pulses.

    messages (sequence of RC6Message)
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

    pulse_width = 444.0e-6 # 444us pulse width
    
    yield (t, 0) # set initial conditions; idle-low
    t += idle_start

    for msg in messages:
        msg_bits = [1] # Start bit
        msg_bits.extend(split_bits(msg.mode, 3))
        msg_bits.extend([2, 2]) # Place-holders for the toggle bit
        if msg.customer is not None and msg.mode == 6:
            if msg.customer > 127:
                msg_bits.append(1) # 15-bit customer
                msg_bits.extend(split_bits(msg.customer, 15))
            else:
                msg_bits.append(0) # 7-bit customer
                msg_bits.extend(split_bits(msg.customer, 7))
            
        msg_bits.extend(split_bits(msg.addr, 8))
        msg_bits.extend(split_bits(msg.cmd, 8))

        #print('\n### synth msg_bits:', msg_bits)

        coded_bits = ((1, 0) if b else (0, 1) for b in msg_bits) # Expand each bit into a pair of half bits
        coded_bits = [b for sl in coded_bits for b in sl] # Flatten the tuples
        coded_bits[8:12] = (1, 1, 0, 0) if msg.toggle else (0, 0, 1, 1) # Add toggle bit

        #print('### synth coded_bits:', coded_bits)
        coded_bits = [1, 1, 1, 1, 1, 1, 0, 0] + coded_bits # Add AGC leader

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


