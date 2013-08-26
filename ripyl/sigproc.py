#!/usr/bin/python
# -*- coding: utf-8 -*-

'''General routines for signal processing of streaming waveforms
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

from __future__ import print_function

import itertools
from ripyl.streaming import SampleChunk, StreamError, ChunkExtractor

import numpy as np
import scipy.signal as signal


def samples_to_sample_stream(raw_samples, sample_period, start_time=0.0, chunk_size=1000):
    '''Convert raw samples to a chunked sample stream

    This is a generator function that can be used in a pipeline of waveform
    procesing operations

    raw_samples (iterable of numbers)
        The samples to convert to a sample stream.
    
    sample_period (float)
        The time interval between samples

    start_time (float)
        The time for the first sample

    chunk_size (int)
        The maximum number of samples for each chunk

    Yields a series of SampleChunk objects representing the time and
      sample value for each input sample. This can be fed to functions
      that expect a chunked sample stream as input.
    '''
    t = start_time
    for i in xrange(0, len(raw_samples), chunk_size):
        chunk = np.asarray(raw_samples[i:i + chunk_size], dtype=float)
        sc = SampleChunk(chunk, t, sample_period)

        yield sc
        t += sample_period * len(chunk)




def remove_excess_edges(edges):
    '''Remove incorrect edge transitions from an edge stream
    
    This is a generator function.
    
    This function is most useful for conditioning the outputs of the protocol
    synthesizers. For those protocols with multiple signals, the synthesizers
    myst yield a new output set for *all* signals when any *one* of them changes.
    This results in non-conforming edge streams that contain multiple consecutive
    pairs with a non-changing value.
    
    edges (iterable of (float, int) tuples)
        An edge stream to filter for extraneous non-edges
        
    Yields an edge stream.
    '''
    prev_state = None
    last_e = None
    for e in edges:
        if prev_state is None:
            prev_state = e[1]
            yield e
        else:
            if e[1] != prev_state:
                prev_state = e[1]
                last_e = None
                yield e
            else: # Save last edge so we can yield it at the end
                last_e = e
        
    if last_e is not None:
        yield last_e


def edges_to_sample_stream(edges, sample_period, end_extension=None, chunk_size=1000):
    '''Convert an edge stream to a sample stream
    
    edges (iterable of (float, int) tuples)
        An edge stream to sample
        
    sample_period (float)
        The sample period for converting the edge stream
        
    end_extension (float)
        Optional amount of time to add to the end after the last edge transition
    
    Yields a sample stream.
    '''
    t = 0.0
    
    try:
        cur_states = next(edges)
        next_states = next(edges)
    except StopIteration:
        raise StreamError('Not enough edges to generate samples')
    
    t = cur_states[0]
    chunk = np.empty(chunk_size, dtype=float)
    chunk_count = 0
    start_time = cur_states[0]

    while True:
        while t < next_states[0]:
            chunk[chunk_count] = cur_states[1]
            chunk_count += 1
            
            t += sample_period
            if chunk_count == chunk_size:
                yield SampleChunk(chunk, start_time, sample_period)

                chunk = np.empty(chunk_size, dtype=float)
                chunk_count = 0
                start_time = t
        
        cur_states = next_states
        try:
            next_states = next(edges)
        except StopIteration:
            break
            
    if end_extension is not None:
        end_time = t + end_extension
        while t < end_time:
            chunk[chunk_count] = cur_states[1]
            chunk_count += 1

            t += sample_period
            if chunk_count == chunk_size:
                yield SampleChunk(chunk, start_time, sample_period)

                chunk = np.empty(chunk_size, dtype=float)
                chunk_count = 0
                start_time = t

    if chunk_count > 0:
        yield SampleChunk(chunk[:chunk_count], start_time, sample_period)


def min_rise_time(sample_rate):
    '''Compute the minimum rise time for a sample rate

    This function is useful to determine the minimum rise time acceptable as parameters
    to filter_waveform() and synth_wave(). You should use a scale factor to incease the rise
    time at least slightly (e.g. rt * 1.01) to avoid raising a ValueError in those functions
    due to floating point inaccuracies.

    sample_rate (number)
        The sample rate to determine rise time from

    Returns a float for the minimum acceptable rise time.
    '''

    return 0.35 * 2.0 / sample_rate

def approximate_bandwidth(rise_time):
    '''Determine an approximate bandwidth for a signal with a known rise time

    rise_time (float)
        A rise time to compute bandwidth from

    Returns the bandwidth for the rise time.
    '''
    return 0.35 / rise_time
    
    
def filter_waveform(samples, sample_rate, rise_time, ripple_db=60.0, pool_size=1000, chunk_size=1000):
    '''Apply a bandwidth limiting low-pass filter to a sample stream
    
    This is a generator function.
    
    samples (iterable of SampleChunk objects)
        An iterable sample stream to be filtered.
    
    sample_rate (float)
        The sample rate for converting the sample stream.
    
    rise_time (float)
        Rise (and fall) time for the filtered samples.
    
    ripple_db (float)
        Noise suppression in dB for the bandwidth filter stop band. This should
        be a positive value.
        
    pool_size (int)
        Internal FIR filter sample pool size. This can generally be ignored. To support
        streaming of samples, the FIR filter operation is done piecewise so we don't have
        to consume the entire input before producing filtered output. Larger values will
        reduce the number of filter operations performed. Excessively small values will
        waste time due to the reprocessing of overlapping samples between successive pools.
    
    Yields a sample stream.
    '''

    sample_period = 1.0 / sample_rate
    nyquist = sample_rate / 2.0
    edge_bw = approximate_bandwidth(rise_time)
    transition_bw = edge_bw * 4.0 # This gives a nice smooth transition with no Gibbs effect
    cutoff_hz = edge_bw
    
    if cutoff_hz > nyquist:
        min_rise = min_rise_time(sample_rate)
        raise ValueError('Rise time is too fast for current sample rate (min: {0})'.format(min_rise))
    
    N, beta = signal.kaiserord(ripple_db, transition_bw / nyquist)
    taps = signal.firwin(N, cutoff_hz / nyquist, window=('kaiser', beta))
    
    # Filter delay
    delay = 0.5 * (N-1) / sample_rate
    
    if pool_size < 2*N:
        pool_size = 2*N

    stream_ended = False

    # Get a pool of samples
    spool = np.zeros((pool_size + N-1,), dtype = np.float)
    sc = next(samples)
    s_ix = 0
    spool[0:N//2-1] += sc.samples[0] # Pad the first part of the pool with a copy of the first sample
    
    # Prime the initial portion of the pool with data that will be filtered out
    pool_start_time = sc.start_time + delay
    fresh_pool = False

    for i in xrange(N//2 - 1, N-1):
        try:
            next_sample = sc.samples[s_ix]
            spool[i] = next_sample

            s_ix += 1
            if s_ix >= len(sc.samples):
                s_ix = 0
                sc = next(samples)

        except StopIteration:
            stream_ended = True
            break
    
    valid_samples = 0
    
    while not stream_ended:
        # Fill the pool with samples
        if fresh_pool:
            pool_start_time = sc.start_time + s_ix * sc.sample_period
            #print('## pst:', pool_start_time, pool_start_time + delay, s_ix)
            fresh_pool = False
        for i in xrange(N-1, pool_size + N-1):
            try:
                next_sample = sc.samples[s_ix]
                spool[i] = next_sample

                valid_samples = i

                s_ix += 1
                if s_ix >= len(sc.samples):
                    s_ix = 0
                    sc = next(samples)

            except StopIteration:
                stream_ended = True
                break
                
        filt = signal.lfilter(taps, 1.0, spool[:valid_samples+1])
        
        # copy end samples to start of pool
        if not stream_ended:
            spool[0:N-1] = spool[pool_size:pool_size + N-1]
        
        yield SampleChunk(filt[N-1:valid_samples+1], pool_start_time, sample_period)
        fresh_pool = True


def synth_wave(edges, sample_rate, rise_time, ripple_db=60.0):
    '''Convert an edge stream to a sampled waveform with band limited rise/fall times
    
    This is a convenience function combining edges_to_sample_stream() and
    filter_waveform().
    
    edges (sequence of (float, int) tuples)
        An edge stream to be sampled
    
    sample_rate (float)
        The sample rate for converting the edge stream
    
    rise_time (float)
        Rise (and fall) time for the filtered samples
    
    ripple_db (float)
        Noise suppression in dB for the bandwidth filter stop band. This should
        be a positive value.

    
    Returns an iterator for the synthesized sample stream
    '''
    sample_period = 1.0 / sample_rate

    samples = edges_to_sample_stream(edges, sample_period)

    return filter_waveform(samples, sample_rate, rise_time, ripple_db)

    
def noisify(samples, snr_db=30.0):
    '''Add noise to a sample stream
    
    This modifies samples with additive, normally distributed noise
    
    This is a generator function.
    
    samples (iterable of SampleChunk objects)
        An iterable sample stream to modify.

    snr_db (float)
        The Signal to Noise Ratio in dB. This value is only accurate if the
        input samples are normalized to the range 0.0 to 1.0. Any amplification
        should be applied after noisify() for the SNR to be correct.

    Yields a sample stream.
    '''

    if snr_db > 80.0:
        for sc in samples:
            yield sc
    else:
        # SNR = mean / std. dev.
        # std. dev. = mean / SNR --> 0.5 / SNR
        noise_sd = 0.5 / (10.0 ** (snr_db / 20.0))

        for sc in samples:
            sc.samples += np.random.normal(0.0, noise_sd, len(sc.samples))
            yield sc


def quantize(samples, full_scale, bits=8):
    '''Quantize samples to simulate oscilloscope quantization error
    
    This should be applied to a noisy signal to have notable results.
    
    samples (iterable of SampleChunk objects)
        An iterable sample stream to modify.
        
    full_scale (float)
        The full scale range for digitizer being emulated. For example,
        a scope with 8 vertical divisions set at 2V/div. will have a
        full scale range of 2V*8 = 16V
    
    bits (int)
        The number of bits to quantize to

    Yields a sample stream.
    '''

    ulp = float(full_scale) / 2**bits

    for sc in samples:
        sc.samples = np.floor(sc.samples / full_scale * 2**bits) * ulp
        yield sc


def amplify(samples, gain=1.0, offset=0.0):
    '''Apply gain and offset to a sample stream
    
    This modifies samples such that output = input * gain + offset.
    
    This is a generator function.
    
    samples (iterable of SampleChunk objects)
        An iterable sample stream to modify.
    
    gain (float)
        The gain multiplier for the samples
    
    offset (float)
        The additive offset for the samples
    
    Yields a sample stream.
    '''

    for sc in samples:
        sc.samples *= gain
        sc.samples += offset
        yield sc

       
def dropout(samples, start_time, end_time, val=0.0):
    '''Force a sample stream to a fixed level
    
    This simulates the effect of a dropout in data transmission by
    repacing samples with a fixed value.
    
    This is a generator function.
    
    samples (iterable of SampleChunk objects)
        An iterable sample stream to modify.
    
    start_time (float)
        Start of the dropout phase
    
    end_time (float)
        End of the dropout phase
    
    val (float)
        The sample value to substitute during the dropout phase

    Yields a sample stream.
    '''

    for sc in samples:
        sc_end_time = sc.start_time + len(sc.samples) * sc.sample_period
        if sc_end_time < start_time or sc.start_time > end_time:
            yield sc
            continue

        if start_time > sc.start_time:
            start_ix = int((start_time - sc.start_time) / sc.sample_period)
        else:
            start_ix = 0

        if end_time < sc_end_time:
            end_ix = int((end_time - sc.start_time) / sc.sample_period) + 1
        else:
            end_ix = len(sc.samples)

        sc.samples[start_ix:end_ix] = val
        yield sc


def invert(stream):
    '''Invert the polarity of stream values
    
    This is a generator function.
    
    samples (iterable of SampleChunk objects)
        An iterable sample stream to modify.
    
    Yields a sample stream.
    '''

    for sc in stream:
        sc.samples *= -1.0
        yield sc

        
def sum_streams(stream1, stream2):
    '''Add two sample streams together
    
    The time elements of each stream will not be aligned if they do not match.
    Instead the time values from stream1 are used for the result. The iterator
    terminates when either of the two streams ends.
    
    This is a generator function.
    
    stream1 (iterable of SampleChunk objects)
    stream2 (iterable of SampleChunk objects)
        The two sample streams to have their corresponding values added together.
        
    Yields a sample stream.
    '''

    ex1 = ChunkExtractor(stream1)
    ex2 = ChunkExtractor(stream2)

    while True:
        c1 = ex1.next_chunk()
        c2 = ex2.next_chunk()

        if c1 is None or c2 is None:
            break

        if len(c1.samples) != len(c2.samples):
            size = min(len(c1.samples), len(c2.samples))
            c1.samples = c1.samples[:size] + c2.samples[:size]
        else:
            c1.samples += c2.samples

        yield c1



def chain(stream_gap_time, *streams):
    '''Combine a sequence of sample streams together.

    A set of sample streams are concatenated together with updated time
    stamps to maintain monotonically increasing time.

    stream_gap_time (float)
        The time interval added between successive streams

    streams (sequence of iterables containing SampleChunk objects)
        A sequence of streams

    Yields a sample stream representing the data from each stream in order
    '''
    offset = 0.0
    sc_end_time = 0.0

    for stream in streams:
        for sc in stream:
            sc.start_time += offset
            sc_end_time = sc.start_time + len(sc.samples) * sc.sample_period
            yield sc

        offset = sc_end_time + stream_gap_time


def chain_edges(stream_gap_time, *streams):
    '''Combine a sequence of edge streams together.

    A set of edge streams are concatenated together with updated time
    stamps to maintain monotonically increasing time.

    stream_gap_time (float)
        The time interval added between successive streams

    streams (sequence of sequences containing (float, number) tuples)
        A sequence of streams

    Yields an edge stream representing the data from each stream in order
    '''
    offset = 0.0
    fixed_time = 0.0
    for s in streams:
        for p in s:
            fixed_time = p[0] + offset
            yield (fixed_time, p[1])
        offset = fixed_time + stream_gap_time


