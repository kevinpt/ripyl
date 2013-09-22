#!/usr/bin/python
# -*- coding: utf-8 -*-

'''NEC IR protocol decoder
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

class NECMessage(object):
    '''NEC infrared message'''
    def __init__(self, cmd, addr_low, addr_high=None, cmd_inv=None):
        self.addr_low = addr_low
        self.addr_high = (~addr_low) & 0xFF if addr_high is None else addr_high

        self.cmd = cmd
        self.cmd_inv = (~cmd) & 0xFF if cmd_inv is None else cmd_inv

    def is_valid(self):
        '''Return True if the command check byte is correct'''
        valid = True
        if self.cmd != ((~self.cmd_inv) & 0xFF): valid = False
        return valid

    def __repr__(self):
        if self.addr_high == (~self.addr_low) & 0xFF:
            return 'NECMessage(cmd={}, addr_low={})'.format(self.cmd, self.addr_low)
        else:
            return 'NECMessage(cmd={}, addr_low={}, addr_high={})'.format(self.cmd, self.addr_low, self.addr_high)

    def __eq__(self, other):
        return vars(self) == vars(other)

    def __ne__(self, other):
        return not (self == other)
            

class NECRepeat(NECMessage):
    '''NEC infrared repeat command'''
    def __init__(self):
        NECMessage.__init__(self, -1, -1, -1, -1)

    def is_valid(self):
        return True

    def __repr__(self):
        return 'NECRepeat()'
    
    def __str__(self):
        return '(repeat)'


class NECStreamMessage(stream.StreamSegment):
    '''Message object for NEC data'''
    def __init__(self, bounds, data=None, status=stream.StreamStatus.Ok):
        stream.StreamSegment.__init__(self, bounds, data, status=status)
        self.kind = 'NEC message'




def nec_decode(ir_stream, carrier_freq=38.0e3, polarity=ir.IRConfig.IdleLow, logic_levels=None, \
     stream_type=stream.StreamType.Samples):

    '''Decode NEC infrared protocol

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
        
    Yields a series of NECStreamMessage objects.
      
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

    epsilon = 30.0e-6 # Allow +/-30us variation for pulses and bit times
    time_is_nearly = functools.partial(ir.time_is_nearly, epsilon=epsilon)
    time_is_at_least = functools.partial(ir.time_is_at_least, epsilon=epsilon)

    while not es.at_end():
        # Look for the falling edge of an AGC burst
        if es.cur_state() == 0:
            es.advance_to_edge() # Now we're 1

        es.advance_to_edge() # Now we're 0. Could be end of AGC
        ts = es.advance_to_edge() # Start of next pulse

        # Measure the time we skipped forward by
        if time_is_nearly(ts, 2.25e-3) or time_is_nearly(ts, 4.5e-3):
            # Previous pulse was AGC (gap between 2.25ms and 4.5ms)
            msg_start_time = es.cur_time - ts - 9.0e-3

            if time_is_at_least(ts, 4.5e-3): # command message

                msg_bits = []
                bit_starts = []
            
                while len(msg_bits) < 32:
                    bit_start_time = es.cur_time

                    ts = es.advance_to_edge()
                    if time_is_nearly(ts, 560.0e-6): # 560us bit pulse time
                        # Measure next time gap to determine if bit is 1 or 0
                        ts = es.advance_to_edge()
                        bit_period = es.cur_time - bit_start_time
                        if time_is_nearly(bit_period, 2.25e-3): # 1-bit
                            msg_bits.append(1)
                            bit_starts.append(bit_start_time)

                        if time_is_nearly(bit_period, 1.12e-3): # 0-bit
                            msg_bits.append(0)
                            bit_starts.append(bit_start_time)
                    else:
                        break

                if len(msg_bits) == 32:
                    bit_starts.append(es.cur_time) # End of last byte


                    # Check for the stop bit
                    ts = es.advance_to_edge()
                    if time_is_nearly(ts, 560.0e-6): # 560us stop pulse time
                        # Valid command message

                        msg_bytes = [join_bits(reversed(msg_bits[i:i+8])) for i in xrange(0, 32, 8)]
                        m_bounds = [(bit_starts[i], bit_starts[i+8]) for i in xrange(0, 32, 8)]

                        addr_low = msg_bytes[0]
                        addr_high = msg_bytes[1]
                        cmd = msg_bytes[2]
                        cmd_inv = msg_bytes[3]

                        nec_msg = NECMessage(cmd, addr_low, addr_high, cmd_inv)
                        sm = NECStreamMessage((msg_start_time, es.cur_time), nec_msg)
                        sm.annotate('frame', {}, stream.AnnotationFormat.Hidden)

                        sm.subrecords.append(stream.StreamSegment((m_bounds[0][0], m_bounds[0][1]), addr_low, kind='addr-low'))
                        sm.subrecords[-1].annotate('addr', {'_bits':8})
                        sm.subrecords.append(stream.StreamSegment((m_bounds[1][0], m_bounds[1][1]), addr_high, kind='addr-high'))
                        sm.subrecords[-1].annotate('addr', {'_bits':8})
                        sm.subrecords.append(stream.StreamSegment((m_bounds[2][0], m_bounds[2][1]), cmd, kind='cmd'))
                        sm.subrecords[-1].annotate('data', {'_bits':8})

                        status = stream.StreamStatus.Ok if cmd == (~cmd_inv) & 0xFF else stream.StreamStatus.Error
                        sm.subrecords.append(stream.StreamSegment((m_bounds[3][0], m_bounds[3][1]), cmd_inv, kind='cmd-inv', status=status))
                        sm.subrecords[-1].annotate('check', {'_bits':8})


                        yield sm

            else: # repeat message
                # Check for the stop bit
                ts = es.advance_to_edge()
                if time_is_nearly(ts, 560.0e-6): # 560us stop pulse time
                    # Valid repeat message
                    sm = NECStreamMessage((msg_start_time, es.cur_time), NECRepeat())
                    sm.annotate('frame', {'name':''}, stream.AnnotationFormat.String)
                    yield sm
            


def nec_synth(messages, idle_start=0.0, message_interval=42.5e-3, idle_end=1.0e-3):
    '''Generate synthesized NEC Infrared waveforms
    
    This function simulates NEC IR pulses.

    messages (sequence of NECMessage)
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
    irtx = 0 # idle-low
    
    yield (t, irtx) # set initial conditions; idle-low
    t += idle_start

    for msg in messages:
        irtx = 1 # start AGC burst
        yield (t, irtx)

        t += 9.0e-3 # 9ms
        irtx = 0
        yield (t, irtx)

        if msg.cmd == -1 and msg.addr_low == -1: # this is a repeat message
            t += 2.25e-3 # 2.25ms

        else: # command message
            t += 4.5e-3 # 4.5ms

            msg_bytes = (split_bits(msg.addr_low, 8), split_bits(msg.addr_high, 8), \
                split_bits(msg.cmd, 8), split_bits(~msg.cmd, 8))

            msg_bits = [bit for b in msg_bytes for bit in reversed(b)]
            
            for bit in msg_bits:
                # output initial 560us pulse
                irtx = 1
                yield (t, irtx)

                t += 560.0e-6
                irtx = 0
                yield (t, irtx)

                if bit == 1:
                    t += 2.25e-3 - 560.0e-6
                else:
                    t += 1.12e-3 - 560.0e-6

        # output stop pulse
        irtx = 1
        yield (t, irtx)

        t += 560.0e-6
        irtx = 0
        yield (t, irtx)

        t += message_interval

    t += idle_end - message_interval
        
    yield (t, irtx)


