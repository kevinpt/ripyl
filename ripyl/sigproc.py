#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Protocol decode library
   General routines for signal processing of streaming waveforms
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

import itertools

import numpy as np
import scipy as sp
import scipy.signal as signal


def samples_to_sample_stream(raw_samples, sample_period, start_time=0.0):
    '''Convert raw samples to a sample stream

    This is a generator function that can be used in a pipeline of waveform
    procesing operations

    raw_samples
        An iterable of sample values
    
    sample_period
        The floating point time interval between samples
    
    start_time
        The floating point time for the first sample

    Yields a series of 2-tuples (time, value) representing the time and
      sample value for each input sample. This can be fed to functions
      that expect a sample stream as input.
    '''
    t = start_time
    for s in raw_samples:
        yield(t, s)
        t += sample_period


def remove_excess_edges(edges):
    '''Remove incorrect edge transitions from an edge stream
    
    This is a generator function.
    
    This function is most useful for conditioning the outputs of the protocol
    synthesizers. For those protocols with multiple signals, the synthesizers
    myst yield a new output set for *all* signals when any *one* of them changes.
    This results in non-conforming edge streams that contain multiple consecutive
    pairs with a non-changing value.
    
    edges
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
    
    edges
        An edge stream to sample
        
    sample_rate
        Floating point sample rate for converting the edge stream
        
    end_extension
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

    
    
def filter_waveform(samples, sample_rate, rise_time, ripple_db=60.0, pool_size=1000):
    '''Apply a bandwidth limiting low-pass filter to a sample stream
    
    This is a generator function.
    
    samples
        A sample stream to be filtered.
    
    sample_rate
        Floating point sample rate for converting the edge stream.
    
    rise_time
        Rise (and fall) time for the filterd samples.
    
    ripple_db
        Noise suppression in dB for the bandwidth filter stop band. This should
        be a positive value.
        
    pool_size
        Internal FIR filter sample pool size. This can generally be ignored. To support
        streaming of samples, the FIR filter operation is done piecewise so we don't have
        to consume the entire input before producing filtered output. Larger values will
        reduce the number of filter operations performed. Excessively small values will
        waste time due to the reprocessing of overlapping samples between successive pools.
    
    Yields a sample stream.
    '''

    nyquist = sample_rate / 2.0
    edge_bw = 0.35 / rise_time
    transition_bw = edge_bw * 4.0 # This gives a nice smooth transition with no Gibbs effect
    cutoff_hz = edge_bw
    
    if cutoff_hz > nyquist:
        min_rise = 0.35 / nyquist
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
    
    edges
        An edge stream to be sampled
    
    sample_rate
        Floating point sample rate for converting the edge stream
    
    rise_time
        Rise (and fall) time for the filterd samples
    
    ripple_db
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
    
    samples
        An iterable sample stream of (time, value) pairs.

    snr_db
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


def amplify(samples, gain=1.0, offset=0.0):
    '''Apply gain and offset to a sample stream
    
    This modifies samples such that output = input * gain + offset.
    
    This is a generator function.
    
    samples
        An iterable sample stream of (time, value) pairs.
    
    gain
        The gain multiplier for the samples
    
    offset
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
    
    samples
        An iterable sample stream of (time, value) pairs.
    
    start_time
        Start of the dropout phase
    
    end_time
        End of the dropout phase
    
    val
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
    
    stream
        An iterable of stream (time, value) pairs. The stream can either be samples
        or a diferential edge stream containing (-1, 0, 1) values that must be
        inverted.
    
    Yields a stream of inverted elements
    '''
    for s in stream:
        yield (s[0], -s[1])

        
def sum_streams(stream1, stream2):
    '''Add two sample streams together
    
    The time elements of each stream will not be aligned if they do not patch.
    Instead the time values from stream1 are used for the result. The iterator
    terminates when either of the two streams ends.
    
    This is a generator function.
    
    stream1
    stream2
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
