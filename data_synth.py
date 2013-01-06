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

def add_noise(samples, snr_db=30.0):
    if snr_db > 80.0:
        return samples
    else:
        noise_sd = 0.5 / (10.0 ** (snr_db / 20.0))
        noise = np.random.normal(0.0, noise_sd, len(samples))
        return samples + noise

        
def synth_wave(edges, sample_rate, rise_time, gain=1.0, offset=0.0, snr_db=30.0, ripple_db=60.0):
    sample_period = 1.0 / sample_rate
    
    samples = sample_edge_list(edges, sample_period)
    filtered, t = filter_edges(samples, sample_rate, rise_time, ripple_db)
    noisy = add_noise(filtered, snr_db)
    
    return (noisy * gain + offset, t)
        
if __name__ == '__main__':
    rise_time = 1.0e-6
    sample_rate = 10.0e6
    #sample_rate = 4.0 / rise_time
    print('sample rate', sample_rate)
    # edge_bw = 0.35 / rise_time
    
    # print('edge bandwidth: {0:,}'.format(edge_bw))
    
    edges = serial_synth('Hello world!', 115200.0)
    
    # text_data = 'hello'
    # baud = 115200
    # bit_period = 1.0 / baud
    # byte_spacing = 100.0e-7
    
    # print('min sample rate: {0}'.format(4 / bit_period))
    

    # sample_period = 1.0 / sample_rate
    
    # edges = []
    # cur_time = 0.0
    # cur_level = 1
    
    # edges.append((cur_time, cur_level))
    # for i,c in enumerate(text_data):
        # cur_time += byte_spacing
        # cur_level = 0
        # edges.append((cur_time, cur_level)) # falling edge of start bit
        # cur_time += bit_period
        # bits = [int(b) for b in bin(ord(c))[2:]]
        # for b in bits[::-1]:
            # if b != cur_level:
                # cur_level = b
                # edges.append((cur_time, cur_level))
            # cur_time += bit_period
            
        # if cur_level == 0: # add stop bit
            # cur_level = 1
            # edges.append((cur_time, cur_level))
        # cur_time += 2.0 * bit_period
        # cur_time += byte_spacing
        
    # edges.append((cur_time, cur_level))
    
    
    # convert edge list to list of samples
    # v = sample_edge_list(edges, sample_period)
    
    # t = 0.0
    # total_samples = int(edges[-1][0] / sample_period)
    # print('{0:,} samples'.format(total_samples))
    # v = [1] * total_samples
    # e_ix = 0
    # cur_state = edges[e_ix]
    # next_edge = edges[e_ix+1][0]
    # for i in xrange(total_samples):
        # if t > next_edge:
            # e_ix += 1
            # cur_state = edges[e_ix]
            # next_edge = edges[e_ix+1][0]
        # v[i] = cur_state[1]
        # t += sample_period

        
    # filter the sampled waveform
    # nyquist = sample_rate / 2.0
    # transition_bw = edge_bw * 3.0 #5.0e6
    # ripple_db = 60.0
    # cutoff_hz = edge_bw
    # print('nyquist', nyquist, 'transition_bw', transition_bw, 'cutoff_hz', cutoff_hz)
    
    # N, beta = signal.kaiserord(ripple_db, transition_bw / nyquist)
    # taps = signal.firwin(N, cutoff_hz / nyquist, window=('kaiser', beta))
    # filtered = signal.lfilter(taps, 1.0, v)[N-1:]
    
    # print('{0} taps'.format(len(taps)))
    # filtered = filter_edges(v, sample_rate, rise_time)
    

    # noisy = add_noise(filtered)
    # noisy = noisy * 5.0 + 1.5
    
    noisy, t = synth_wave(edges, sample_rate, rise_time, gain=2.0, offset=0.0, snr_db=30, ripple_db=60)
    #t = np.arange(len(noisy)) / sample_rate
    
    print('{0} samples'.format(len(noisy)))
        
    # plt.plot(t, noisy)
    # plt.ylim(-0.05, 1.75)
    # plt.show()
    
    #plt.figure(2)
    #plt.plot(sp.fft(noisy)[:len(noisy)/2])
    
    # params = find_digital_params(noisy)
    # found_edges = find_edges(noisy, params)
    # print(len(edges), len(found_edges))
    # raw_symbol_rate = find_symbol_rate(found_edges, sample_rate)
    # print(raw_symbol_rate)

    print(edges[:10])
    
    frames = serial_decode_2(noisy, t, sample_rate, inverted=True, baud_rate=None)
    print(''.join(str(d) for d in frames))
    
    # for f in frames:
        # print(repr(f))
        # for sf in f.subframes:
            # print('  {0}'.format(repr(sf)))
        
    
    
    plt.figure(2)
    #plt.plot(s)
    
    
    #plt.show()
    
    