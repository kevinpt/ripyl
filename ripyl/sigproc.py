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
from ripyl.streaming import StreamError, StreamChunk

import numpy as np
import scipy.signal as signal


def samples_to_sample_stream(raw_samples, sample_period, start_time=0.0):
    '''Convert raw samples to a sample stream

    This is a generator function that can be used in a pipeline of waveform
    procesing operations

    raw_samples (sequence of numbers)
        An iterable of sample values
    
    sample_period (float)
        The time interval between samples
    
    start_time (float)
        The time for the first sample

    Yields a series of 2-tuples (time, value) representing the time and
      sample value for each input sample. This can be fed to functions
      that expect a sample stream as input.
    '''
    t = start_time
    for s in raw_samples:
        yield(t, s)
        t += sample_period

def samples_to_chunked_sample_stream(raw_samples, sample_period, chunk_size=1000, start_time=0.0):
    '''Convert raw samples to a chunked sample stream

    This is a generator function that can be used in a pipeline of waveform
    procesing operations

    raw_samples (sequence of numbers)
        An iterable of sample values
    
    sample_period (float)
        The time interval between samples

    chunk_size (int)
        The maximum number of samples for each chunk
    
    start_time (float)
        The time for the first sample

    Yields a series of StreamChunk objects representing the time and
      sample value for each input sample. This can be fed to functions
      that expect a chunked sample stream as input.
    '''
    t = start_time
    for i in xrange(0, len(raw_samples), chunk_size):
        chunk = np.asarray(raw_samples[i:i + chunk_size], dtype=float)
        sc = StreamChunk(chunk, t, sample_period)

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
    
    edges (sequence of (float, int) tuples)
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

def edges_to_sample_stream(edges, sample_period, end_extension=None):
    '''Convert an edge stream to a sample stream
    
    edges (sequence of (float, int) tuples)
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

    while True:
        while t < next_states[0]:
            yield (t, cur_states[1])
            t += sample_period
        
        cur_states = next_states
        try:
            next_states = next(edges)
        except StopIteration:
            break
            
    if end_extension is not None:
        end_time = t + end_extension
        while t < end_time:
            yield(t, cur_states[1])
            t += sample_period


def min_rise_time(sample_rate):
    '''Compute the minimum rise time for a sample rate

    This function is useful to determine the minimum rise time acceptable as parameters
    to filter_waveform() and synth_wave(). You should use a scale factor to incease the rise
    time at least slightly (e.g. rt * 1.01) to avoid raising a ValueError in those functions
    due to floating point inaccuracies.

    sample_rate (int)
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
    
    
def filter_waveform(samples, sample_rate, rise_time, ripple_db=60.0, pool_size=1000):
    '''Apply a bandwidth limiting low-pass filter to a sample stream
    
    This is a generator function.
    
    samples (sequence of (float, number) tuples)
        A sample stream to be filtered.
    
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
    samp_it, init_it = itertools.tee(samples)
    spool[0:N//2-1] += next(init_it)[1] # Pad the first part of the pool with a copy of the first sample
    del init_it
    
    tpool = np.zeros((pool_size + N-1,), dtype = np.float)
    
    # Prime the initial portion of the pool with data that will be filtered out
    for i in xrange(N//2 - 1, N-1):
        try:
            tpool[i], spool[i] = next(samp_it)
        except StopIteration:
            stream_ended = True
            break
    
    valid_samples = 0
    
    while not stream_ended:
        # Fill the pool with samples
        for i in xrange(N-1, pool_size + N-1):
            try:
                tpool[i], spool[i] = next(samp_it)
                valid_samples = i
            except StopIteration:
                stream_ended = True
                break
                
        filt = signal.lfilter(taps, 1.0, spool[:valid_samples+1])
        
        # copy end samples to start of pool
        if not stream_ended:
            spool[0:N-1] = spool[pool_size:pool_size + N-1]
        
        tpool[N-1:] -= delay
        
        for i in xrange(N-1, valid_samples+1):
            yield (tpool[i], filt[i])


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
    
    samples (sequence of (float, number) tuples)
        An iterable sample stream of (time, value) pairs.

    snr_db (float)
        The Signal to Noise Ratio in dB. This value is only accurate if the
        input samples are normalized to the range 0.0 to 1.0. Any amplification
        should be applied after noisify() for the SNR to be correct.

    Yields a sample stream.
    '''

    # SNR = mean / std. dev.
    # std. dev. = mean / SNR --> 0.5 / SNR
    noise_sd = 0.5 / (10.0 ** (snr_db / 20.0))
    np_len = 1000
    np_ix = np_len
    
    for s in samples:
        if snr_db > 80.0:
            yield s
        else:
            if np_ix == np_len:
                noise_pool = np.random.normal(0.0, noise_sd, np_len)
                np_ix = 0
            
            noise = noise_pool[np_ix]
            np_ix += 1
            
            yield (s[0], s[1] + noise)


def quantize(samples, full_scale, bits=8):
    '''Quantize samples to simulate oscilloscope quantization error
    
    This should be applied to a noisy signal to have notable results.
    
    samples (sequence of (float, number) tuples)
        An iterable sample stream of (time, value) pairs.
        
    full_scale (float)
        The full scale range for digitizer being emulated. For example,
        a scope with 8 vertical divisions set at 2V/div. will have a
        full scale range of 2V*8 = 16V
    
    bits (int)
        The number of bits to quantize to

    Yields a sample stream.
    '''

    ulp = full_scale / 2**bits
    
    for s in samples:
        q = int(s[1] / full_scale * 2**bits) * ulp
        yield (s[0], q)


def amplify(samples, gain=1.0, offset=0.0):
    '''Apply gain and offset to a sample stream
    
    This modifies samples such that output = input * gain + offset.
    
    This is a generator function.
    
    samples (sequence of (float, number) tuples)
        An iterable sample stream of (time, value) pairs.
    
    gain (float)
        The gain multiplier for the samples
    
    offset (float)
        The additive offset for the samples
    
    Yields a sample stream.
    '''
    for s in samples:
        yield (s[0], s[1] * gain + offset)
        

def dropout(samples, start_time, end_time, val=0.0):
    '''Force a sample stream to a fixed level
    
    This simulates the effect of a dropout in data transmission by
    repacing samples with a fixed value.
    
    This is a generator function.
    
    samples (sequence of (float, number) tuples)
        An iterable sample stream of (time, value) pairs.
    
    start_time (float)
        Start of the dropout phase
    
    end_time (float)
        End of the dropout phase
    
    val (float)
        The sample value to substitute during the dropout phase

    Yields a sample stream.
    '''
    for s in samples:
        if s[0] >= start_time and s[0] < end_time:
            yield (s[0], val)
        else:
            yield s


def invert(stream):
    '''Invert the polarity of stream values
    
    This is a generator function.
    
    stream (sequence of (float, number) tuples)
        An iterable of stream (time, value) pairs. The stream can either be samples
        or a diferential edge stream containing (-1, 0, 1) values that must be
        inverted.
    
    Yields a stream of inverted elements
    '''
    for s in stream:
        yield (s[0], -s[1])

        
def sum_streams(stream1, stream2):
    '''Add two sample streams together
    
    The time elements of each stream will not be aligned if they do not match.
    Instead the time values from stream1 are used for the result. The iterator
    terminates when either of the two streams ends.
    
    This is a generator function.
    
    stream1 (sequence of (float, number) tuples)
    stream2 (sequence of (float, number) tuples)
        The two sample streams to have their corresponding values added together.
        
    Yields a sample stream.
    '''
    while True:
        try:
            ns1 = next(stream1)
            ns2 = next(stream2)
            yield (ns1[0], ns1[1] + ns2[1])
            
        except StopIteration:
            break


def chain(stream_gap_time, *streams):
    '''Combine a sequence of streams together.

    A set of sample or edge streams are concatenated together with updated time
    stamps to maintain monotonically increasing time.

    stream_gap_time (float)
        The time interval added between successive streams

    streams (sequence of sequences containing (float, number) tuples)
        A sequence of streams

    Yields a stream representing the data from each stream in order
    '''
    offset = 0.0
    fixed_time = 0.0
    for s in streams:
        for p in s:
            fixed_time = p[0] + offset
            yield (fixed_time, p[1])
        offset = fixed_time + stream_gap_time


