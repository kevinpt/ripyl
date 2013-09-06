#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Sony SIRC IR protocol decoder
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
from ripyl.util.enum import Enum
from ripyl.util.bitops import split_bits, join_bits

import ripyl.protocol.infrared as ir

class SIRCMessage(object):
    '''SIRC infrared message'''
    def __init__(self, cmd, device, extended=None):
        self.cmd = cmd
        self.device = device
        self.extended = extended

    def __repr__(self):
        if self.extended is None:
            return 'SIRCMessage({}, {})'.format(self.cmd, self.device)
        else:
            return 'SIRCMessage({}, {}, {})'.format(self.cmd, self.device, self.extended)

    def __eq__(self, other):
        return vars(self) == vars(other)

    def __ne__(self, other):
        return not (self == other)

            

class SIRCStreamMessage(stream.StreamSegment):
    '''Stream message object for SIRC data'''
    def __init__(self, bounds, data=None, status=stream.StreamStatus.Ok):
        stream.StreamSegment.__init__(self, bounds, data, status=status)
        self.kind = 'SIRC message'




def sirc_decode(ir_stream, carrier_freq=40.0e3, polarity=ir.IRConfig.IdleLow, logic_levels=None, \
     stream_type=stream.StreamType.Samples):

    '''Decode Sony SIRC infrared protocol

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
        
    Yields a series of SIRCStreamMessage objects.
      
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

    mod_period = (1.0 / carrier_freq) # Not really important. Just need a default value to pass to EdgeSequence
    es = decode.EdgeSequence(edges, mod_period)

    epsilon = 30.0e-6 # allow +/-30us variation for pulses and bit times
    time_is_nearly = functools.partial(ir.time_is_nearly, epsilon=epsilon)
    time_is_at_least = functools.partial(ir.time_is_at_least, epsilon=epsilon)

    one_t = 600.0e-6 # 600us 1T time

    while not es.at_end():
        # Look for the falling edge of a start pulse
        if es.cur_state() == 0:
            es.advance_to_edge() # Now we're 1

        ts = es.advance_to_edge() # Now we're 0. Could be end of start pulse

        # Measure the time we skipped forward by
        if not time_is_nearly(ts, 4 * one_t):
            continue # Not a start pulse


        msg_start_time = es.cur_time - ts
        msg_bits = []
        bit_starts = []
        prev_edge = 0.0

        # Accumulate bits until idle for too long
        while True:
            prev_edge = es.cur_time
            ts = es.advance_to_edge()
            if not time_is_nearly(ts, one_t):
                break  # Not the beginning of a bit

            bit_starts.append(es.cur_time - ts)

            ts = es.advance_to_edge()
            if time_is_nearly(ts, one_t): # 0-bit
                msg_bits.append(0)

            elif time_is_nearly(ts, 2 * one_t): #1-bit
                msg_bits.append(1)

            else:
                break

        bit_starts.append(prev_edge) # End of last bit
        #print('### last bit:', es.cur_time)

        if len(msg_bits) in (12, 15, 20):
            cmd = join_bits(reversed(msg_bits[0:7]))
            cmd_range = (bit_starts[0], bit_starts[7])

            if len(msg_bits) == 12 or len(msg_bits) == 20:
                device = join_bits(reversed(msg_bits[7:12]))
                device_range = (bit_starts[7], bit_starts[12])
            else: # 15-bit command
                device = join_bits(reversed(msg_bits[7:15]))
                device_range = (bit_starts[7], bit_starts[15])

            extended = None
            if len(msg_bits) == 20: # 20-bit extended format
                extended = join_bits(reversed(msg_bits[12:20]))
                extended_range = (bit_starts[12], bit_starts[20])
                
            msg = SIRCMessage(cmd, device, extended)
            sm = SIRCStreamMessage((msg_start_time, prev_edge + 0.5*one_t), msg)

            cmd_ss = stream.StreamSegment((cmd_range[0], cmd_range[1]), cmd, kind='command')
            sm.subrecords.append(cmd_ss)
            sm.subrecords[-1].annotate('data', {'_bits':7})

            dev_ss = stream.StreamSegment((device_range[0], device_range[1]), device, kind='device')
            sm.subrecords.append(dev_ss)
            sm.subrecords[-1].annotate('addr')
            if len(msg_bits) == 15:
                sm.subrecords[-1].fields['_bits'] = 8
            else:
                sm.subrecords[-1].fields['_bits'] = 5

            if extended is not None:
                ext_ss = stream.StreamSegment((extended_range[0], extended_range[1]), extended, kind='extended')
                sm.subrecords.append(ext_ss)
                sm.subrecords[-1].annotate('data', {'_bits':8})


            yield sm
                



def sirc_synth(messages, idle_start=0.0, message_interval=42.5e-3, idle_end=1.0e-3):
    '''Generate synthesized Sony SIRC Infrared waveforms
    
    This function simulates SIRC IR pulses.

    messages (sequence of SIRCMessage)
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
    ir = 0 # idle-low

    one_t = 600.0e-6 # 600us 1T time
    
    yield (t, ir) # set initial conditions
    t += idle_start

    for msg in messages:

        msg_bits = list(reversed(split_bits(msg.cmd, 7)))
        if msg.device < 2**5 or msg.extended is not None:
            msg_bits.extend(reversed(split_bits(msg.device, 5)))
        else: # 15-bit command with 8-bit device field
            msg_bits.extend(reversed(split_bits(msg.device, 8)))

        if msg.extended is not None:
            msg_bits.extend(reversed(split_bits(msg.extended, 8)))
        

        ir = 1 # start pulse burst
        yield (t, ir)

        t += 4 * one_t # 4T pulse
        ir = 0
        yield (t, ir)

        for bit in msg_bits:
            t += one_t # 1T space
            ir = 1
            yield (t, ir)

            t += (bit+1) * one_t # 1T or 2T pulse
            ir = 0
            yield (t, ir)

        t += one_t # 1T space
        t += message_interval
            
    t += idle_end - message_interval
        
    yield (t, ir) # Final state


