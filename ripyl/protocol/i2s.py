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


def i2s_decode(sck, sd, ws, word_size, cpol=0, wspol=0, msb_justified=True, \
    channels=2, i2s_variant=I2SVariant.Standard, data_offset=1, logic_levels=None, \
    stream_type=stream.StreamType.Samples):

    '''Decode an I2S data stream

    This is a generator function that can be used in a pipeline of waveform
    processing operations.
    
    The sck, sd, and ws parameters are edge or sample streams.
    Sample streams are a sequence of SampleChunk Objects. Edge streams are a sequence
    of 2-tuples of (time, int) pairs. The type of stream is identified by the stream_type
    parameter. Sample streams will be analyzed to find edge transitions representing
    0 and 1 logic states of the waveforms. With sample streams, an initial block of data
    on the sck stream is consumed to determine the most likely logic levels in the signal.

    sck (iterable of SampleChunk objects or (float, int) pairs)
        A sample stream or edge stream representing an I2S clock signal
    
    sd  (iterable of SampleChunk objects or (float, int) pairs)
        A sample stream or edge stream representing an I2S data signal.
    
    ws  (iterable of SampleChunk objects or (float, int) pairs or None)
        A sample stream or edge stream representing an I2S word select signal.
    
    cpol (int)
        Clock polarity: 0 or 1 (the idle state of the clock signal)

    wspol (int)
        Word select polarity: 0 or 1. Only applies to Standard variant

    msb_justified (bool)
        Position of word bits within a frame. Only applies to Standard variant.

    channels (int)
        Number of channels. Must be either 1 or 2.

    i2s_variant (I2SVariant)
        The type of I2S protocol to decode. Can be one of Standard, DSPModeShort or
        DSPModeLong.

    data_offset (int)
        Number of cycles data is delayed from the start of frame indicated by ws.

    logic_levels ((float, float) or None)
        Optional pair that indicates (low, high) logic levels of the sample
        stream. When present, auto level detection is disabled. This has no effect on
        edge streams.

    stream_type (streaming.StreamType)
        A StreamType value indicating that the clk, data_io, and cs parameters represent either Samples
        or Edges

    Yields a series of I2SFrame objects.

    Raises AutoLevelError if stream_type = Samples and the logic levels cannot
      be determined.

    Supported formats::

        : Standard I2S:
        : sck -._,-._,-._,-._,-._,-._,-._,-._,-._,-._,-._,-._,-._,-._,-._
        : ws  -._______________________,-----------------------._________
        : sd  _____<===X===X===X===>_______<===X===X===X===>_______<===X=
        :      |   | Chan 0        |       |Chan 1         |
        :      |   |
        :        /\--- data_offset (1 cycle in original standard)
        : 
        : LSB justified:
        : sd  _________<===X===X===X===>_______<===X===X===X===>_______<=
        :              |  Word size    |
        :      |                 Frame size                    |
        : 
        : 
        : DSP mode (short pulses)
        : sck -._,-._,-._,-._,-._,-._,-._,-._,-._,-._,-._,-._,-._,-._,-._
        : ws  _,---.___________________________________________,---._____
        : sd  _____<===X===X===X===X===X===X===X===>_______________<===X=
        :          | Chan 0        | Chan 1        |
        : 
        : DSP mode (long pulses)
        : sck -._,-._,-._,-._,-._,-._,-._,-._,-._,-._,-._,-._,-._,-._,-._
        : ws  _,-------------------------------._______________,---------
        : sd  _____<===X===X===X===X===X===X===X===>_______________<===X=
        :          | Chan 0        | Chan 1        |

    '''

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


    if i2s_variant == I2SVariant.Standard:
        if channels == 1:
            frame_start_pol = (wspol, 1 - wspol) # Frames start on both edges
        else: # 2 channels
            frame_start_pol = (wspol,)

    else: # DSPMode
        wspol = 1
        frame_start_pol = (wspol,)
    

    edge_sets = {
        'sck': sck_it,
        'sd': sd_it,
        'ws': ws_it
    }
    
    es = MultiEdgeSequence(edge_sets, 0.0)

    bitq = []
    start_time = None
    end_time = None
    bit_starts = []
    in_frame = False
    prev_ws = None
    bit_delay = 0
    next_bit_delay = 0
    active_frame = False
    frame_cycles = 0
    raw_size = None
    sample_shift = [0] * channels
    sample_mask = (2 ** word_size) - 1

    # Begin to decode
    
    while not es.at_end():
        _, cname = es.advance_to_edge()
        if in_frame and cname == 'sck' and not es.at_end('sck') and es.cur_state('sck') == 1:
            if bit_delay > 0:
                next_bit_delay = bit_delay - 1

            if bit_delay == 0 or active_frame: # Collect bits from frame
                active_frame = True
                bitq.append(es.cur_state('sd'))
                end_time = es.cur_time()
                bit_starts.append(es.cur_time())
                frame_cycles += 1


            bit_delay = next_bit_delay


            # Detect if WS toggled over the last clock period
            if prev_ws != es.cur_state('ws') and es.cur_state('ws') in frame_start_pol:
                if raw_size is None:
                    # Calculate parameters used to locate the data bits within a frame
                    raw_size = frame_cycles + (data_offset - 1)

                    frame_size = raw_size // channels if i2s_variant == I2SVariant.Standard else raw_size

                    if i2s_variant == I2SVariant.Standard:
                        justify_shift = frame_size - word_size if msb_justified else 0
                        for c in xrange(channels):
                            sample_shift[c] = justify_shift + frame_size * (channels - 1 - c)
                    else: # DSPMode
                        for c in xrange(channels):
                            sample_shift[c] = frame_size - (word_size * (c + 1))

            prev_ws = es.cur_state('ws')

            if len(bitq) >= raw_size and raw_size is not None:

                full_word = join_bits(bitq[:raw_size])
                samples = []
                bounds = []
                for c in xrange(channels):
                    samples.append((full_word >> sample_shift[c]) & sample_mask)
                    # Determine the bounds for this sample
                    start_bit = raw_size - (sample_shift[c] + word_size)
                    end_bit = start_bit + word_size - 1
                    half_bit = (bit_starts[end_bit] - bit_starts[start_bit]) / (word_size-1) / 2
                    bounds.append((bit_starts[start_bit] - half_bit, bit_starts[end_bit] + half_bit))

                frame_data = samples[0] if len(samples) == 1 else tuple(samples)

                end_time = bit_starts[raw_size-1] + half_bit
                nf = I2SFrame((start_time, end_time), frame_data)
                nf.annotate('frame', {}, stream.AnnotationFormat.Hidden)

                for c in xrange(channels):
                    nf.subrecords.append(stream.StreamSegment(bounds[c], samples[c], kind='channel' + str(c)))
                    nf.subrecords[-1].annotate('data', {'_bits':word_size}, stream.AnnotationFormat.Hex)

                yield nf

                start_time = end_time
                bitq = bitq[raw_size:]
                bit_starts = bit_starts[raw_size:]


        # Find start of frame at falling edge of WS
        if not in_frame and cname == 'ws' and not es.at_end('ws') and es.cur_state('ws') in frame_start_pol:
            in_frame = True
            start_time = es.cur_time()
            bit_delay = data_offset
            prev_ws = es.cur_state('ws')


def stereo_to_mono(samples):
    '''Convert stero samples to mono

    samples (sequence of 2-tuples of int)
        The stereo samples to convert

    Yields a sequence of int
    '''
    for s in samples:
        try:
            if len(s) > 0:
                for c in s:
                    yield c
        except TypeError: # Not a sequence
            yield s

def _duplicate(samples):
    for s in samples:
        yield s
        yield s

def mono_to_stereo(samples, duplicate_samples=True):
    '''Convert mono samples to stereo

    samples (sequence of int)
        The mono samples to convert

    duplicate_samples (bool)
        Duplicates incoming samples when True

    Yields a sequence of 2-tuples of int
    '''
    if duplicate_samples:
        samples = _duplicate(samples)

    args = [iter(samples)] * 2
    return itertools.izip(*args)


def i2s_synth(data, word_size, frame_size, sample_rate, cpol=0, wspol=0, msb_justified=True,
    channels=2, i2s_variant=I2SVariant.Standard, data_offset=1, idle_start=0.0, idle_end=0.0):
    '''Generate synthesized I2S waveforms

    This function simulates the transmission of data over I2S

    This is a generator function that can be used in a pipeline of waveform
    processing operations.

    data (sequence of int or 2-tuples of int)
        Sequence of words that will be transmitted serially. Elements should be int
        when number of channels is 1. Should be a 2-tuple when channels is 2.

    word_size (int)
        The number of bits in each word

    frame_size (int)
        The number of bits in each frame. When variant is Standard the frame size
        covers all word and padding bits for one channel. For the DSPMode variants
        the frame size covers all word and padding bits for all channels.

    sample_rate (float)
        Sample rate for the data stream. The clock frequency is derived from this rate
        based on the selected variant, frame_size, and number of channels.
    
    cpol (int)
        Clock polarity: 0 or 1 (the idle state of the clock signal)

    wspol (int)
        Word select polarity: 0 or 1. Only applies to Standard variant

    msb_justified (bool)
        Position of word bits within a frame. Only applies to Standard variant.

    channels (int)
        Number of channels. Must be either 1 or 2.

    i2s_variant (I2SVariant)
        The type of I2S protocol to decode. Can be one of Standard, DSPModeShort or
        DSPModeLong.

    data_offset (int)
        Number of cycles data is delayed from the start of frame indicated by ws.

    idle_start (float)
        The amount of idle time before the transmission of data begins

    idle_end (float)
        The amount of idle time after the last transmission

    Yields a triplet of pairs representing the three edge streams for sck, sd, and ws
      respectively. Each edge stream pair is in (time, value) format representing the
      time and logic value (0 or 1) for each edge transition. The first set of pairs
      yielded is the initial state of the waveforms.
    '''
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
    else: # Standard variant
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


    sample_shift = [0] * channels
    sample_mask = (2 ** word_size) - 1
    if i2s_variant == I2SVariant.Standard:
        clock_freq = sample_rate * channels * frame_size
        justify_shift = frame_size - word_size if msb_justified else 0
        for c in xrange(channels):
            sample_shift[c] = justify_shift + frame_size * (1 - c)
    else: # DSPMode
        clock_freq = sample_rate * frame_size
        for c in xrange(channels):
            sample_shift[c] = frame_size - (word_size * (c + 1))

    half_bit_period = 1.0 / (2.0 * clock_freq)


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


