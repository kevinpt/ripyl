#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Data synthesizer
'''

from __future__ import print_function, division
from optparse import OptionParser

import matplotlib.pyplot as plt
import matplotlib.patches as pts

import numpy as np
import scipy as sp
import scipy.signal as signal

from decode import *
from streaming import *
from spi import *
from uart import *

    

def test_spi():
    cpol = 0
    cpha = 0
    clk, mosi, cs = zip(*list(spi_synth([3, 64], 8, 1.0, cpol, cpha, True, 2.0, 0.0)))
    
    #print('CLK:', clk)
    #print( 'MOSI:', mosi)
    #print('CS:', cs)
    clk = list(remove_excess_edges(iter(clk)))
    mosi = list(remove_excess_edges(iter(mosi)))
    cs = list(remove_excess_edges(iter(cs)))
    
    use_edges=False

    if use_edges:
        frames = spi_decode_2(iter(clk), iter(mosi), iter(cs), cpol=cpol, cpha=cpha, lsb_first=True, stream_type=StreamType.Edges)    
        frames = list(frames)
        
        print('$$$ MOSI', mosi[:10])
        print('$$$ CS', cs[:10])
        
        ct, clk_wf = zip(*list(sample_edge_list(iter(clk), 0.1)))
        mt, mosi_wf = zip(*list(amplify(sample_edge_list(iter(mosi), 0.1), 0.8, 0.1)))
        st, cs_wf = zip(*list(amplify(sample_edge_list(iter(cs), 0.1), 0.6, 0.2)))

        plt.clf()
        plt.plot(ct, clk_wf)
        plt.plot(mt, mosi_wf)
        plt.plot(st, cs_wf)
        plt.ylim(-0.05, 1.25)
        
    else:
    
        #frames = spi_decode_2(iter(clk), iter(mosi), iter(cs), cpol=cpol, cpha=cpha, lsb_first=True)
        sr = 1.0e-2
        # #print('>>>>>', len(list(sample_edge_list(iter(clk), sr))))
        # ct, clk_wf = zip(*list(sample_edge_list(iter(clk), sr)))
        # print('logic>', find_logic_levels(noisify(sample_edge_list(iter(clk), sr)), max_samples=10000))
        # plt.plot(ct, clk_wf)
        # plt.show()

        clk_s = list(noisify(sample_edge_list(iter(clk), sr)))
        mosi_s = list(noisify(sample_edge_list(iter(mosi), sr)))
        cs_s = list(noisify(sample_edge_list(iter(cs), sr)))
        
        frames = spi_decode_2(iter(clk_s), iter(mosi_s), iter(cs_s), cpol=cpol, cpha=cpha, lsb_first=True)
        
        frames = list(frames)
        
        ct, clk_wf = zip(*clk_s)
        mt, mosi_wf = zip(*mosi_s)
        st, cs_wf = zip (*cs_s)
        
        logic = find_logic_levels(iter(clk_s), max_samples=5000)
        clk_e = list(find_edges(iter(clk_s), logic, hysteresis=0.4))
        mosi_e = list(find_edges(iter(mosi_s), logic, hysteresis=0.4))
        cs_e =   list(find_edges(iter(cs_s), logic, hysteresis=0.4))
        
        print('$$$ MOSI', mosi_e[:10])
        print('$$$ CS', cs_e[:10])
        #ce_t, clk_e_wf = zip(*list(clk_e))
        
        # #print(clk_wf[:100])

        plt.clf()
        plt.plot(ct, clk_wf)
        plt.plot(mt, mosi_wf)
        plt.plot(st, cs_wf)
        #plt.plot(ce_t, clk_e_wf)
        plt.ylim(-0.05, 1.25)

    print('Decoded:', [str(f) for f in frames])
        
    ax = plt.axes()
    text_height = 1.05
    rect_top = 1.15
    rect_bot = -0.05
    for f in frames:
        plt.text((f.start_time + f.end_time) / 2.0, text_height, str(f))
        color = 'orange' if f.nested_status() < 200 else 'red'
        rect = pts.Rectangle((f.start_time, rect_bot), width=f.end_time - f.start_time, height=rect_top - rect_bot, facecolor=color,  alpha=0.2)
        ax.add_patch(rect)    
    
    plt.show()

def test_uart():

    rise_time = 1.0e-6
    sample_rate = 10.0e6
    #sample_rate = 4.0 / rise_time
    print('sample rate', sample_rate)
    # edge_bw = 0.35 / rise_time
    
    # print('edge bandwidth: {0:,}'.format(edge_bw))
    
    #edges = serial_synth('Hello world!', 115200.0)
    #edges = uart_synth('He', 57600.0)
    edges = uart_synth_2(bytearray('Hello world???'), 8, 115200.0, parity='even', idle_start=100.0e-7)
    
    
    samples = synth_wave(edges, sample_rate, rise_time, ripple_db=60)
    
    noisy = amplify(noisify(samples, snr_db=30.0), gain=-15.0)
    
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
    
    waveform = list(noisy) #list(dropout(noisy,2.0e-3,2.1e-3))
    t, wf = zip(*waveform)

    
    frames = uart_decode(iter(waveform), inverted=False, parity='even', baud_rate=None)
    frames = list(frames)
    print(''.join(str(d) for d in frames))

    plt.plot(t, wf)
    ax = plt.axes()
    
    
    logic = find_logic_levels(iter(waveform), 5000)
    span = logic[1] - logic[0]
    rect_top = logic[1] + span * 0.15
    rect_bot = logic[0] - span * 0.05
    
    text_height = logic[1] + rect_top / 2.0
    
    plt.ylim(rect_bot - span * 0.1, rect_top + span * 0.1)
    
    print('Logic levels:', logic)
    
    for f in frames:
        plt.text((f.start_time + f.end_time) / 2.0, text_height, str(f))
        color = 'orange' if f.nested_status() < 200 else 'red'
        rect = pts.Rectangle((f.start_time, rect_bot), width=f.end_time - f.start_time, height=rect_top - rect_bot, facecolor=color,  alpha=0.2)
        ax.add_patch(rect)

    hist, _ = np.histogram(wf, bins=60)
    hpeaks = find_hist_peaks(hist)
    print('## hpeaks', hpeaks)
    
    b, t = find_bot_top_hist_peaks(wf[:5000], 60)
    print('## b, t', b, t)
        
    plt.figure(2)
    plt.hist(wf, bins=60)
    
    plt.show()
    

    
    # print('End time:', frames[-1].end_time)
    # for x in frames:
        # pass
        # print('fc', x.data, chr(x.data))
    
    # for f in frames:
        # print(repr(f))
        # for sf in f.subframes:
            # print('  {0}'.format(repr(sf)))
        
    
    
    #plt.figure(2)
    #plt.plot(s)
    
    
    #plt.show()
    
        
    

def sample_edge_list(edges, sample_period):
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
        


# def add_noise(samples, snr_db=30.0):
    # if snr_db > 80.0:
        # return samples
    # else:
        # noise_sd = 0.5 / (10.0 ** (snr_db / 20.0))
        # noise = np.random.normal(0.0, noise_sd, len(samples))
        # return samples + noise

        

def synth_wave(edges, sample_rate, rise_time, ripple_db=60.0):
    sample_period = 1.0 / sample_rate
    
    samples = sample_edge_list(edges, sample_period)
    
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
    filtered = filter_edges(samples, sample_rate, rise_time, ripple_db)
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

        
def dropout(samples, start_time, end_time, val=0.0):
    for s in samples:
        if s[0] > start_time and s[0] < end_time:
            yield (s[0], val)
        else:
            yield s

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
        
    if not last_e is None:
        yield last_e


if __name__ == '__main__':
    print('Serial decode test tool')

    parser = OptionParser()
    parser.add_option('-u', dest='uart', action='store_true', default=False, help='uart test')
    parser.add_option('-s', dest='spi', action='store_true', default=False, help='spi test')
    
    options, args = parser.parse_args()
    
    if options.uart:
        print('  Testing UART')
        test_uart()
        
    if options.spi:
        print('  Testing SPI')
        test_spi()

