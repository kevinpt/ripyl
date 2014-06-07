#!/usr/bin/python
# -*- coding: utf-8 -*-

'''I2S protocol decoder
'''

# Copyright © 2014 Kevin Thibedeau

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
from ripyl.util.enum import Enum
from collections import deque

class I2SVariant(Enum):
    Standard = 0 # Original Philips specification
    DSPModeShortSync = 1 # One cycle WS pulse indicating start of frame
    DSPModeLongSync = 2 # WS pulse functions as data valid indicator


class I2SFrame(stream.StreamSegment):
    '''Frame object for I2S data'''
    def __init__(self, bounds, data):
        '''
        bounds ((float, float))
            2-tuple (start_time, end_time) for the bounds of the frame
        
        data (sequence of int)
            Data representing the sample(s) in the frame
        '''
        stream.StreamSegment.__init__(self, bounds, data)
        self.kind = 'I2S frame'
        self.word_size = None
        
    def __str__(self):
        return str(self.data)


def i2s_decode(sck, sd, ws, word_size, frame_size=None, cpol=0, wspol=0, msb_justified=True, \
    channels=2, i2s_variant=I2SVariant.Standard, data_offset=1, logic_levels=None, \
    stream_type=stream.StreamType.Samples):

    if stream_type == stream.StreamType.Samples:
        if logic_levels is None:
            s_sck_it, logic_levels = check_logic_levels(sck)
        else:
            s_sck_it = sck
        
        hyst = 0.4
        sck_it = find_edges(s_sck_it, logic_levels, hysteresis=hyst)
        sd_it = find_edges(sd, logic_levels, hysteresis=hyst)
        ws_it = find_edges(ws, logic_levels, hysteresis=hyst)

    else: # The streams are already lists of edges
        sck_it = sck
        sd_it = sd
        ws_it = ws

    # Invert clock if rising edge is active
    if cpol == 1:
        sck_it = ((t, 1 - e) for t, e in sck_it)


    raw_size = 2 * frame_size if i2s_variant == I2SVariant.Standard else frame_size

    sample_shift = [0] * channels
    sample_mask = (2 ** word_size) - 1
    if i2s_variant == I2SVariant.Standard:
        justify_shift = frame_size - word_size if msb_justified else 0
        for c in xrange(channels):
            sample_shift[c] = justify_shift + frame_size * (1 - c)
    else: # DSPMode
        for c in xrange(channels):
            sample_shift[c] = frame_size - (word_size * (c + 1))
    

    edge_sets = {
        'sck': sck_it,
        'sd': sd_it,
        'ws': ws_it
    }
    
    es = MultiEdgeSequence(edge_sets, 0.0)

    bitq = []
    start_time = None
    end_time = None
    in_frame = False
    prev_ws = None

    # Begin to decode
    
    while not es.at_end():
        _, cname = es.advance_to_edge()
        if in_frame and cname == 'sck' and not es.at_end('sck'):
            if es.cur_state('sck') == 1: # Rising edge
                bitq.append(es.cur_state('sd'))
                end_time = es.cur_time()

                if len(bitq) == raw_size + data_offset:
                    print('@@@  bits:', start_time, bitq[-raw_size:]) #FIXME
                    full_word = join_bits(bitq[-raw_size:])
                    samples = []
                    for c in xrange(channels):
                        samples.append((full_word >> sample_shift[c]) & sample_mask)

                    print('@@@ ', [hex(s) for s in samples])
                        

                if prev_ws == 1 and es.cur_state('ws') == 0:
                    # Falling edge of WS -> start of new frame
                    print('#### bits:', start_time, bitq) #FIXME

                    bitq = [0] * data_offset
                    start_time = es.cur_time()

                prev_ws = es.cur_state('ws')

        # Find start of frame
        if not in_frame and cname == 'ws' and not es.at_end('ws') and es.cur_state('ws') == 0:
            in_frame = True
            start_time = es.cur_time()



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


            



def stereo_to_mono(samples):
  for s in samples:
    try:
      if len(s) > 0:
        for c in s:
          yield c
    except TypeError: # Not a sequence
      yield s

def duplicate(samples):
    for s in samples:
      yield s
      yield s

def mono_to_stereo(samples, duplicate_samples=True):
    if duplicate_samples:
        samples = duplicate(samples)

    args = [iter(samples)] * 2
    return itertools.izip(*args)


def i2s_synth(data, word_size, frame_size, sample_rate, cpol=0, wspol=0, msb_justified=True,
    channels=2, i2s_variant=I2SVariant.Standard, data_offset=1, idle_start=0.0, idle_end=0.0):
    # This is a wrapper around the actual synthesis code in _i2s_synth()
    # It unzips the yielded tuple and removes unwanted artifact edges

    sck, sd, ws = itertools.izip(*_i2s_synth(data, word_size, frame_size, sample_rate, cpol, \
        wspol, msb_justified, channels, i2s_variant, data_offset, idle_start, idle_end))

    sck = remove_excess_edges(sck)
    sd = remove_excess_edges(sd)
    ws = remove_excess_edges(ws)
    return sck, sd, ws


def _i2s_synth(data, word_size, frame_size, sample_rate, cpol=0, wspol=0, msb_justified=True,
    channels=2, i2s_variant=I2SVariant.Standard, data_offset=1, idle_start=0.0, idle_end=0.0):

    if i2s_variant == I2SVariant.DSPModeLongSync:
        assert word_size * channels < frame_size, 'channels * word size must be less than the frame size'
    elif i2s_variant == I2SVariant.DSPModeShortSync:
        assert word_size * channels <= frame_size, 'channels * word size must not be greater than the frame size'
    else:
        assert word_size <= frame_size, 'Word size must not be greater than the frame size'

    if i2s_variant in (I2SVariant.DSPModeLongSync, I2SVariant.DSPModeShortSync):
        wspol = 1

    if channels == 1 and i2s_variant == I2SVariant.Standard:
        data = mono_to_stereo(data, duplicate_samples=False)
        channels = 2

    t = 0.0
    sck = 1 - cpol
    sd = 0
    ws = 1 - wspol

    clock_freq = sample_rate * channels * frame_size
    half_bit_period = 1.0 / (2.0 * clock_freq)

    sample_shift = [0] * channels
    sample_mask = (2 ** word_size) - 1
    if i2s_variant == I2SVariant.Standard:
        justify_shift = frame_size - word_size if msb_justified else 0
        for c in xrange(channels):
            sample_shift[c] = justify_shift + frame_size * (1 - c)
    else: # DSPMode
        for c in xrange(channels):
            sample_shift[c] = frame_size - (word_size * (c + 1))


    #print('### shift:', sample_shift)
    #print('### mask:', sample_mask)

    if i2s_variant == I2SVariant.Standard:
        ws_toggle_bits = (0, frame_size)
    elif i2s_variant == I2SVariant.DSPModeShortSync:
        ws_toggle_bits = (0, 1)
    else: # DSPModeLongSync
        ws_toggle_bits = (0, word_size*channels)

    yield ((t, sck), (t, sd), (t, ws)) # Initial conditions
    t += idle_start

    bitq = deque()
    if data_offset > 0:
        bitq.extend([0] * data_offset)

    for s in data:
        if channels == 2:
            word = 0
            for i, c in enumerate(s):
                word += (c & sample_mask) << sample_shift[i]

            bits_size = 2 * frame_size if i2s_variant == I2SVariant.Standard else frame_size

            bits = split_bits(word, bits_size)

        else: # 1 channel
            word = (s & sample_mask) << sample_shift[0]
            bits = split_bits(word, frame_size)

        bitq.extend(bits)
        bits = [bitq.popleft() for _ in bits]
        for i, b in enumerate(bits):
            sd = b
            sck = 1 - sck
            if i in ws_toggle_bits:
                ws = 1 - ws

            yield ((t, sck), (t, sd), (t, ws))
            t += half_bit_period
            sck = 1 - sck
            yield ((t, sck), (t, sd), (t, ws))
            t += half_bit_period

    # Empty remaining bits in the deque
    for b in bitq:
        sd = b
        sck = 1 - sck

        yield ((t, sck), (t, sd), (t, ws))
        t += half_bit_period
        sck = 1 - sck
        yield ((t, sck), (t, sd), (t, ws))
        t += half_bit_period

    t += half_bit_period + idle_end
        
    yield ((t, sck), (t, sd), (t, ws)) # Final state


