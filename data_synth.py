#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Data synthesizer
'''

from __future__ import print_function, division

import matplotlib.pyplot as plt

import numpy as np
import scipy as sp
import scipy.signal as signal

from decode import *


def serial_synth(data, baud=115200, byte_spacing=100.0e-7):
    bit_period = 1.0 / baud
    
    #print('min sample rate: {0}'.format(4 / bit_period))
    
    edges = []
    cur_time = 0.0
    cur_level = 1
    
    edges.append((cur_time, cur_level)) # set initial conditions
    cur_time += byte_spacing
    
    for i,c in enumerate(data):
        cur_level = 0
        edges.append((cur_time, cur_level)) # falling edge of start bit
        cur_time += bit_period
        bits = [int(b) for b in bin(ord(c))[2:].zfill(8)]
        #print('bits', bits)
        for b in bits[::-1]:
            if b != cur_level:
                cur_level = b
                edges.append((cur_time, cur_level))
            cur_time += bit_period
            
        if cur_level == 0: 
            cur_level = 1
            edges.append((cur_time, cur_level))
        cur_time += 2.0 * bit_period # add stop bit
        cur_time += byte_spacing
        
    edges.append((cur_time, cur_level))
    
    return edges

def serial_synth_2(data, baud=115200, stop_bits=1.0, byte_spacing=100.0e-7):
    bit_period = 1.0 / baud
    
    #print('min sample rate: {0}'.format(4 / bit_period))
    
    cur_time = 0.0
    cur_level = 1
    
    yield (cur_time, cur_level) # set initial conditions
    cur_time += byte_spacing
    
    for c in data:
        cur_level = 0
        yield (cur_time, cur_level) # falling edge of start bit
        cur_time += bit_period
        bits = [int(b) for b in bin(ord(c))[2:].zfill(8)]
        #print('bits', bits)
        for b in bits[::-1]:
            if b != cur_level:
                cur_level = b
                yield (cur_time, cur_level)
            cur_time += bit_period
            
        if cur_level == 0: 
            cur_level = 1
            yield (cur_time, cur_level)
        cur_time += stop_bits * bit_period # add stop bit
        cur_time += byte_spacing
        
    #edges.append((cur_time, cur_level))
    yield (cur_time, cur_level)
    
    
def sample_edge_list(edges, sample_period):
    t = 0.0
    total_samples = int(edges[-1][0] / sample_period)
    #print('{0:,} samples'.format(total_samples))
    v = [1] * total_samples
    e_ix = 0
    cur_state = edges[e_ix]
    next_edge = edges[e_ix+1][0]
    for i in xrange(total_samples):
        if t > next_edge:
            e_ix += 1
            cur_state = edges[e_ix]
            next_edge = edges[e_ix+1][0]
        v[i] = cur_state[1]
        t += sample_period
        
    return v

def sample_edge_list_2(edges, sample_period):
    t = 0.0
    
    try:
        cur_states = edges.next()
        next_states = edges.next()
    except StopIteration:
        raise ValueError('Not enough edges to generate samples')
    
    t = cur_states[0]

    while True:
        while t < next_states[0]:
            yield (t, cur_states[1])
            t += sample_period
        
        cur_states = next_states
        try:
            next_states = edges.next()
        except StopIteration:
            break

    
def filter_edges(samples, sample_rate, rise_time, ripple_db=60.0):
    nyquist = sample_rate / 2.0
    edge_bw = 0.35 / rise_time
    transition_bw = edge_bw * 4.0 # this gives a nice smooth transition
    cutoff_hz = edge_bw
    
    if cutoff_hz > nyquist:
        min_rise = 0.35 / nyquist
        raise ValueError('Rise time is too fast for current sample rate (min: {0})'.format(min_rise))
    
    #print('nyquist', nyquist, 'transition_bw', transition_bw, 'cutoff_hz', cutoff_hz)
    
    N, beta = signal.kaiserord(ripple_db, transition_bw / nyquist)
    
    print('cutoff', cutoff_hz, 'nyq', nyquist, cutoff_hz / nyquist)
    
    
    taps = signal.firwin(N, cutoff_hz / nyquist, window=('kaiser', beta))
    filtered = signal.lfilter(taps, 1.0, samples)
    
    delay = 0.5 * (N-1) / sample_rate
    t = (np.arange(len(filtered)) / sample_rate) - delay
    
    return (filtered[N-1:], t[N-1:])

    
def filter_edges_2(samples, sample_rate, rise_time, ripple_db=60.0, pool_size=1000):
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
    print(len(taps), N)
    
    # filter delay
    delay = 0.5 * (N-1) / sample_rate
    print('DE', delay)
    
    if pool_size < 2*N:
        pool_size = 2*N

    stream_ended = False

    # get a pool of samples
    spool = np.zeros((pool_size + N-1,), dtype = np.float)
    samp_it, init_it = itertools.tee(samples)
    spool[0:N//2-1] += init_it.next()[1] # pad the first part of the pool with a copy of the first sample
    del init_it
    
    tpool = np.zeros((pool_size + N-1,), dtype = np.float)
    
    # prime the initial portion of the pool with data that will be filtered out
    for i in xrange(N//2 - 1, N-1):
        try:
            tpool[i], spool[i] = samp_it.next()
        except StopIteration:
            stream_ended = True
            break
    
    valid_samples = 0
    
    while not stream_ended:
        for i in xrange(N-1, pool_size + N-1):
            try:
                tpool[i], spool[i] = samp_it.next()
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
        


def add_noise(samples, snr_db=30.0):
    if snr_db > 80.0:
        return samples
    else:
        noise_sd = 0.5 / (10.0 ** (snr_db / 20.0))
        noise = np.random.normal(0.0, noise_sd, len(samples))
        return samples + noise

        
# def synth_wave(edges, sample_rate, rise_time, gain=1.0, offset=0.0, snr_db=30.0, ripple_db=60.0):
    # sample_period = 1.0 / sample_rate
    
    # samples = sample_edge_list(edges, sample_period)
    # filtered, t = filter_edges(samples, sample_rate, rise_time, ripple_db)
    # noisy = add_noise(filtered, snr_db)
    
    # return (noisy * gain + offset, t)

def synth_wave_2(edges, sample_rate, rise_time, ripple_db=60.0):
    sample_period = 1.0 / sample_rate
    
    samples = sample_edge_list_2(edges, sample_period)
    
    # ot, osamples = zip(*samples)
    # samples = iter(zip(ot, osamples))
    # ofiltered, ot = filter_edges(osamples, sample_rate, rise_time, ripple_db)

    # plt.plot(ot, ofiltered + 0.005)
    
    # t, filtered = zip(*filter_edges_2(samples, sample_rate, rise_time, ripple_db))
    
    # print('##', len(ofiltered), len(filtered))
    # pj = 0.0
    # for i, j in enumerate(t):
        # if j - pj > (1.1  / sample_rate):
            # print('#### missing sample:', i, j)
        # pj = j
    
    # plt.plot(t, filtered)
    # plt.ylim(-0.05, 1.05)
    # plt.show()
    
    #return zip(t, filtered)
    filtered = filter_edges_2(samples, sample_rate, rise_time, ripple_db)
    return filtered
        
def noisify(samples, snr_db=30.0):
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
        
if __name__ == '__main__':
    rise_time = 1.0e-6
    sample_rate = 10.0e6
    #sample_rate = 4.0 / rise_time
    print('sample rate', sample_rate)
    # edge_bw = 0.35 / rise_time
    
    # print('edge bandwidth: {0:,}'.format(edge_bw))
    
    #edges = serial_synth('Hello world!', 115200.0)
    edges = serial_synth_2('Hello world!', 115200.0)
    
    #noisy, t = synth_wave(edges, sample_rate, rise_time, gain=2.0, offset=0.0, snr_db=30, ripple_db=60)
    samples = synth_wave_2(edges, sample_rate, rise_time, ripple_db=60)
    
    noisy = amplify(noisify(samples, snr_db=30.0), gain=-2.0)
    
    #t = np.arange(len(noisy)) / sample_rate
    
    #print('{0} samples'.format(len(noisy)))
        
    # plt.plot(t, noisy)
    # plt.ylim(-0.05, 1.75)
    # plt.show()
    
    #plt.figure(2)
    #plt.plot(sp.fft(noisy)[:len(noisy)/2])

    #print(edges[:10])
    
    #t, o_noisy = zip(*noisy)
    #plt.plot(t, o_noisy)
    #plt.show()
    
    frames = serial_decode(noisy, inverted=False, baud_rate=None)
    print(''.join(str(d) for d in frames))
    
    # for f in frames:
        # print(repr(f))
        # for sf in f.subframes:
            # print('  {0}'.format(repr(sf)))
        
    
    
    #plt.figure(2)
    #plt.plot(s)
    
    
    #plt.show()
    
    