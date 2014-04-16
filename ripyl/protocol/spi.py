#!/usr/bin/python
# -*- coding: utf-8 -*-

'''SPI protocol decoder
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
from ripyl.decode import *
from ripyl.util.bitops import *
from ripyl.sigproc import remove_excess_edges

class SPIFrame(stream.StreamSegment):
    '''Frame object for SPI data'''
    def __init__(self, bounds, data=None):
        '''
        bounds ((float, float))
            2-tuple (start_time, end_time) for the bounds of the frame
        
        data (sequence of int or None)
            Optional data representing the contents of the frame
        '''
        stream.StreamSegment.__init__(self, bounds, data)
        self.kind = 'SPI frame'
        self.word_size = None
        
    def __str__(self):
        return str(self.data)

def spi_decode(clk, data_io, cs=None, cpol=0, cpha=0, lsb_first=True, logic_levels=None, \
    stream_type=stream.StreamType.Samples):
    '''Decode an SPI data stream
    
    This is a generator function that can be used in a pipeline of waveform
    processing operations.
    
    The clk, data_io, and cs parameters are edge or sample streams.
    Sample streams are a sequence of SampleChunk Objects. Edge streams are a sequence
    of 2-tuples of (time, int) pairs. The type of stream is identified by the stream_type
    parameter. Sample streams will be analyzed to find edge transitions representing
    0 and 1 logic states of the waveforms. With sample streams, an initial block of data
    on the clk stream is consumed to determine the most likely logic levels in the signal.

    clk (iterable of SampleChunk objects or (float, int) pairs)
        A sample stream or edge stream representing an SPI clk signal
    
    data_io (iterable of SampleChunk objects or (float, int) pairs)
        A sample stream or edge stream representing an SPI MOSI or MISO signal.
    
    cs (iterable of SampleChunk objects or (float, int) pairs or None)
        A sample stream or edge stream representing an SPI chip select signal.
        Can be None if cs is not available.
    
    cpol (int)
        Clock polarity: 0 or 1 (the idle state of the clock signal)
    
    cpha (int)
        Clock phase: 0 or 1 (data is sampled on the 1st clock edge (0) or the 2nd (1))
    
    lsb_first (bool)
        Flag indicating whether the Least Significant Bit is transmitted first.

    logic_levels ((float, float) or None)
        Optional pair that indicates (low, high) logic levels of the sample
        stream. When present, auto level detection is disabled. This has no effect on
        edge streams.

    stream_type (streaming.StreamType)
        A StreamType value indicating that the clk, data_io, and cs parameters represent either Samples
        or Edges

    Yields a series of SPIFrame objects.
      
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
        data_io_it = find_edges(data_io, logic_levels, hysteresis=hyst)
        if cs is not None:
            cs_it = find_edges(cs, logic_levels, hysteresis=hyst)
        else:
            cs_it = None
    else: # the streams are already lists of edges
        clk_it = clk
        data_io_it = data_io
        cs_it = cs


    edge_sets = {
        'clk': clk_it,
        'data_io': data_io_it
    }
    
    if cs_it is not None:
        edge_sets['cs'] = cs_it
    
    es = MultiEdgeSequence(edge_sets, 0.0)
    
    if cpha == 0:
        active_edge = 1 if cpol == 0 else 0
    else:
        active_edge = 0 if cpol == 0 else 1
    
    bits = []
    start_time = None
    end_time = None
    prev_edge = None
    prev_cycle = None
    
    # begin to decode
    
    while not es.at_end():
        _, cname = es.advance_to_edge()

        
        if cname == 'cs' and not es.at_end('cs'):
            se = stream.StreamEvent(es.cur_time(), data=es.cur_state('cs'), kind='SPI CS')
            yield se

        elif cname == 'clk' and not es.at_end('clk'):
            clk_val = es.cur_state('clk')
            
            if clk_val == active_edge: # capture data bit
                # Check if the elapsed time is more than any previous cycle
                # This indicates that a previous word was complete
                if prev_cycle is not None and es.cur_time() - prev_edge > 1.5 * prev_cycle:
                    if lsb_first:
                        word = join_bits(reversed(bits))
                    else:
                        word = join_bits(bits)
                    
                    nf = SPIFrame((start_time, end_time), word)
                    nf.word_size = len(bits)
                    nf.annotate('frame', {'_bits':len(bits)}, stream.AnnotationFormat.General)
                    
                    bits = []
                    start_time = None
                    
                    yield nf
                    
                # accumulate the bit
                if start_time is None:
                    start_time = es.cur_time()
                    
                bits.append(es.cur_state('data_io'))
                end_time = es.cur_time()
                
                if prev_edge is not None:
                    prev_cycle = es.cur_time() - prev_edge

                prev_edge = es.cur_time()
                
        
    if len(bits) > 0:
        if lsb_first:
            word = join_bits(reversed(bits))
        else:
            word = join_bits(bits)
            
        nf = SPIFrame((start_time, end_time), word)
        nf.word_size = len(bits)
        nf.annotate('frame', {'_bits':len(bits)}, stream.AnnotationFormat.General)
        
        yield nf


    
        
def spi_synth(data, word_size, clock_freq, cpol=0, cpha=0, lsb_first=True, idle_start=0.0, word_interval=0.0, idle_end=0.0):
    '''Generate synthesized SPI waveform
    
    This function simulates a transmission of data over SPI.
    
    This is a generator function that can be used in a pipeline of waveform
    procesing operations.
    
    data (sequence of int)
        A sequence of words that will be transmitted serially
    
    word_size (int)
        The number of bits in each word
    
    clock_freq (float)
        The SPI clock frequency
    
    cpol (int)
        Clock polarity: 0 or 1
    
    cpha (int)
        Clock phase: 0 or 1
    
    lsb_first (bool)
        Flag indicating whether the Least Significant Bit is transmitted first.
    
    idle_start (float)
        The amount of idle time before the transmission of data begins
    
    word_interval (float)
        The amount of time between data words

    idle_end (float)
        The amount of idle time after the last transmission

    Yields a triplet of pairs representing the three edge streams for clk, data_io, and cs
      respectively. Each edge stream pair is in (time, value) format representing the
      time and logic value (0 or 1) for each edge transition. The first set of pairs
      yielded is the initial state of the waveforms.
    '''
    # This is a wrapper around the actual synthesis code in _spi_synth()
    # It unzips the yielded tuple and removes unwanted artifact edges
    clk, data_io, cs = itertools.izip(*_spi_synth(data, word_size, clock_freq, cpol, cpha, \
        lsb_first, idle_start, word_interval, idle_end))
    clk = remove_excess_edges(clk)
    data_io = remove_excess_edges(data_io)
    cs = remove_excess_edges(cs)
    return clk, data_io, cs
    
def _spi_synth(data, word_size, clock_freq, cpol=0, cpha=0, lsb_first=True, idle_start=0.0, word_interval=0.0, idle_end=0.0):
    '''Core SPI sunthesizer
    
    This is a generator function.
    '''

    t = 0.0
    clk = cpol
    data_io = 0
    cs = 1
    
    half_bit_period = 1.0 / (2.0 * clock_freq)
    
    
    yield ((t, clk),(t, data_io),(t, cs)) # initial conditions
    t += idle_start
     
    for i, d in enumerate(data):
        bits_remaining = word_size

        # first bit transmitted will be at the end of the list
        if lsb_first:
            bits = split_bits(d, word_size)
        else:
            bits = list(reversed(split_bits(d, word_size)))
        
        if cpha == 0: # data goes valid a half cycle before the first clock edge
            t += half_bit_period
            data_io = bits[bits_remaining-1]
            bits_remaining -= 1
            cs = 0
            yield ((t, clk),(t, data_io),(t, cs))
            t += half_bit_period
            clk = 1 - clk # initial half clock period
            yield ((t, clk),(t, data_io),(t, cs))
        else:
            t += half_bit_period
            cs = 0
            yield ((t, clk),(t, data_io),(t, cs))
            
        while bits_remaining:
            t += half_bit_period
            clk = 1 - clk
            data_io = bits[bits_remaining-1]
            bits_remaining -= 1
            yield ((t, clk),(t, data_io),(t, cs))

            t += half_bit_period
            clk = 1 - clk
            yield ((t, clk),(t, data_io),(t, cs))
            
        t += half_bit_period
        if cpha == 0: # final half clock period
            clk = 1 - clk
        else: # cpha == 1
            if i == len(data) - 1:  # deassert CS at end of data sequence
                cs = 1
        data_io = 0
        yield ((t, clk),(t, data_io),(t, cs))
        
        if cpha == 0:
            t += half_bit_period
            if i == len(data) - 1: # deassert CS at end of data sequence
                cs = 1
            yield ((t, clk),(t, data_io),(t, cs))
        
            
        t += word_interval
        
    t += half_bit_period + idle_end
        
    yield ((t, clk),(t, data_io),(t, cs)) # final state

