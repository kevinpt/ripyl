#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Protocol decode library
   General routines for signal processing of sampled waveforms
'''

# Copyright © 2012 Kevin Thibedeau

# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:

# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import itertools

import numpy as np
import scipy as sp
import scipy.signal as signal

def remove_excess_edges(edges):
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
            else: # save last edge so we can yield it at the end
                last_e = e
        
    if last_e is not None:
        yield last_e

def sample_edge_list(edges, sample_period, end_extension=None):
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

    
    
def filter_edges(samples, sample_rate, rise_time, ripple_db=60.0, pool_size=1000):
    nyquist = sample_rate / 2.0
    edge_bw = 0.35 / rise_time
    transition_bw = edge_bw * 4.0 # this gives a nice smooth transition
    cutoff_hz = edge_bw
    
    if cutoff_hz > nyquist:
        min_rise = 0.35 / nyquist
        raise ValueError('Rise time is too fast for current sample rate (min: {0})'.format(min_rise))
    
    #print('nyquist', nyquist, 'transition_bw', transition_bw, 'cutoff_hz', cutoff_hz)
    
    N, beta = signal.kaiserord(ripple_db, transition_bw / nyquist)
    
    #print('cutoff', cutoff_hz, 'nyq', nyquist, cutoff_hz / nyquist)
    
    taps = signal.firwin(N, cutoff_hz / nyquist, window=('kaiser', beta))
    #print(len(taps), N)
    
    # filter delay
    delay = 0.5 * (N-1) / sample_rate
    #print('DE', delay)
    
    if pool_size < 2*N:
        pool_size = 2*N

    stream_ended = False

    # get a pool of samples
    spool = np.zeros((pool_size + N-1,), dtype = np.float)
    samp_it, init_it = itertools.tee(samples)
    spool[0:N//2-1] += next(init_it)[1] # pad the first part of the pool with a copy of the first sample
    del init_it
    
    tpool = np.zeros((pool_size + N-1,), dtype = np.float)
    
    # prime the initial portion of the pool with data that will be filtered out
    for i in xrange(N//2 - 1, N-1):
        try:
            tpool[i], spool[i] = next(samp_it)
        except StopIteration:
            stream_ended = True
            break
    
    valid_samples = 0
    
    while not stream_ended:
        for i in xrange(N-1, pool_size + N-1):
            try:
                tpool[i], spool[i] = next(samp_it)
                valid_samples = i
            except StopIteration:
                stream_ended = True
                break
                
        #print('VS', valid_samples, len(tpool))
        
        filt = signal.lfilter(taps, 1.0, spool[:valid_samples+1])
        #print(len(filt), pool_size +N-1)
        ##tpool -= delay
        
        # copy end samples to start of pool
        if not stream_ended:
            spool[0:N-1] = spool[pool_size:pool_size + N-1] #filt[pool_size:pool_size + N-1]
        #tpool[0:N] = tpool[pool_size - 1:pool_size + N-1]
        
        tpool[N-1:] -= delay
        #print('TP', tpool[N-1])
        
        for i in xrange(N-1, valid_samples+1):
            yield (tpool[i], filt[i])


def synth_wave(edges, sample_rate, rise_time, ripple_db=60.0):
    sample_period = 1.0 / sample_rate
    
    samples = sample_edge_list(edges, sample_period)
    
    filtered = filter_edges(samples, sample_rate, rise_time, ripple_db)
    return filtered

    
def noisify(samples, snr_db=30.0):
    # SNR = mean / std. dev.
    # std. dev. = mean / SNR = 0.5 / SNR
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
    for s in samples:
        yield (s[0], s[1] * gain + offset)
        

def dropout(samples, start_time, end_time, val=0.0):
    for s in samples:
        if s[0] > start_time and s[0] < end_time:
            yield (s[0], val)
        else:
            yield s
            
def invert(samples):
    for s in samples:
        yield (s[0], -s[1])

        
def sum_streams(s1, s2):
    while True:
        try:
            ns1 = next(s1)
            ns2 = next(s2)
            yield (ns1[0], ns1[1] + ns2[1])
            
        except StopIteration:
            break
