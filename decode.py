#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Serial decode library
'''

from __future__ import print_function, division

#from collections import Counter
import numpy as np
import scipy as sp
import math
import itertools

        
class online_stats(object):
    ''' Generate statistics from data set
      Computes mean, variance and standard deviation in a single pass throuh
      a data set.
    '''
    def __init__(self):
        self.c = 0
        self.m = 0.0
        self.s = 0.0
        
    def accumulate(self, d):
        self.c += 1
        delta = d - self.m
        self.m = self.m + delta / self.c
        self.s = self.s + delta * (d - self.m)
    
    def variance(self):
        if self.c > 2:
            return self.s / (self.c - 1)
        else:
            return 0.0
    
    def sd(self):
        return math.sqrt(self.variance())
    
    def mean(self):
        return self.m

    def reset(self):
        self.__init__(self)
        


def find_logic_levels(samples, max_samples):
    # get a pool of samples 
    # for now we will get everything up to max_samples
    #FIX: we should do this more intelligently so the tee'd iterator in serial_decode()
    # doesn't have to buffer so much data
    wf = []
    for i in xrange(max_samples):
        wf.append(samples.next()[1])

    # build a histogram of the waveform
    hist, bin_edges = np.histogram(wf, bins=60)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    # We expect a digital waveform to have a strongly bimodal distribution with most
    # samples clustered around the '0' and '1' voltage values
    
    # Split histogram in half so we can find the mode of the '0' and '1' portions
    # and evaluate the skewness as validation
    
    #FIX: implement a better peak finding algorithm
    mid_hist = len(hist) // 2
    low_hist = hist[0:mid_hist]
    low_bins = bin_centers[0:mid_hist]
    high_hist = hist[mid_hist:]
    high_bins = bin_centers[mid_hist:]
    
    # find modes
    #low_mode = max(low_hist, key=lambda tup: tup[1])[0]
    #high_mode = max(high_hist, key=lambda tup: tup[1])[0]
    low_mode = max(zip(low_bins, low_hist), key=lambda tup: tup[1])[0]
    high_mode = max(zip(high_bins, high_hist), key=lambda tup: tup[1])[0]
    
    threshold = (high_mode + low_mode) / 2.0
    
    #print(low_mode, high_mode, threshold)
    
    # Find standard deviation of high and low thresholded data using Welford's method
    os_h = online_stats()
    os_l = online_stats()
    
    #FIX: consider finding a way to avoid iterating over entire waveform once the std. dev.'s have converged
    for i, x in enumerate(wf):
        if x >= threshold: # high data point
            os_h.accumulate(x)

        else: # low data point
            os_l.accumulate(x)

    # Pearson skewness
    ps_l = (os_l.mean() - low_mode) / os_l.sd()
    ps_h = (os_h.mean() - high_mode) / os_h.sd()
    
    #print('Pearson:', ps_l, ps_h)
    # print('p2:', 3 *(m_l - med_l) / sd_l, 3 * (m_h - med_h) / sd_h)
    
    # We will accept any skewness measure below 0.6 as a sign of a digital waveform
    if abs(ps_l) < 0.6 and abs(ps_h) < 0.6:
        return (low_mode, high_mode)
    else:
        return None


def find_edges(samples, logic, hysteresis=0.8):
    span = logic[1] - logic[0]
    thresh = (logic[1] + logic[0]) / 2.0
    hyst_top = span * (0.5 + hysteresis / 2.0) + logic[0]
    hyst_bot = span * (0.5 - hysteresis / 2.0) + logic[0]

    # states
    ES_START = 0
    ES_NEED_POS_EDGE = 1
    ES_NEED_NEG_EDGE = 2
    ES_NEED_HIGH = 3
    ES_NEED_LOW = 4
    
    state = ES_START
    
    # set initial edge state
    start_time, initial_sample = samples.next()
    initial_state = (start_time, 1 if initial_sample > thresh else 0)
    
    #start_time = time_axis[0] if not time_axis is None else 0
    #initial_state = (start_time,1 if wf[0] > thresh else 0)
    
    yield initial_state
    
    #for i, x in enumerate(wf):
    for t, x in samples:
    
        if state == ES_START:
            if x < hyst_bot:
                state = ES_NEED_POS_EDGE
            elif x > hyst_top:
                state = ES_NEED_NEG_EDGE
                
        elif state == ES_NEED_POS_EDGE: # currently below the threshold
            if x >= thresh:
                state = ES_NEED_NEG_EDGE if x > hyst_top else ES_NEED_HIGH
                yield (t,1)

        elif state == ES_NEED_NEG_EDGE: # currently above the the threshold
            if x <= thresh:
                state = ES_NEED_POS_EDGE if x < hyst_bot else ES_NEED_LOW
                yield (t,0)
        
        elif state == ES_NEED_HIGH: # looking for sample above hysteresis threshold
            if x > hyst_top:
                state = ES_NEED_NEG_EDGE
                
        elif state == ES_NEED_LOW: # looking for sample below hysteresis threshold
            if x < hyst_bot:
                state = ES_NEED_POS_EDGE
    
    
def find_symbol_rate(edges, sample_rate=1.0):
    '''
    The edges sequence is a series of 2-tuples containing edge positions and post-edge logic levels.
    The edge positions can either be in absolute time units or integer sample indices. In the
    former case the sample_rate argument should keep its default of 1.0. In the latter, the
    sample_rate must be supplied to convert from span in samples to the final result.
    '''
    e = np.array(zip(*edges)[0]) # get the sample indices of each edge
    spans = e[1:] - e[:-1] # time span (in samples) between successive edges
    
    # generate kernel density estimate of span histogram
    kde = sp.stats.gaussian_kde(spans)
    kde.covariance_factor = lambda: 0.05
    kde._compute_covariance()
    
    # Compute the harmonic product spectrum from the KDE
    # This should leave us with one strong peak for the span corresponding to the
    # fundamental symbol rate
    mv = max(spans) * 1.1 # leave some extra room for the rightmost peak of the KDE
    step = mv / 500
    xs = np.arange(0, mv, step)
    s1 = kde(xs)
    s2 = kde(np.arange(0, mv*2, step*2))[:len(s1)]
    s3 = kde(np.arange(0, mv*3, step*3))[:len(s1)]
    s4 = kde(np.arange(0, mv*4, step*4))[:len(s1)]

     # isolate the findamental span width by using the product
    s = s1 * s2 * s3 * s4

    peak_span = xs[np.argmax(s)] # largest peak from the HPS
    symbol_rate = int(sample_rate / peak_span)
    
    return symbol_rate
    

class edge_sequence(object):
    def __init__(self, edges, time_step, start_time=None):
        self.edges = edges
        self.time_step = time_step
        self.it_end = False
        
        try:
            self.cur_states = self.edges.next()
            self.next_states = self.edges.next()
        except StopIteration:
            self.it_end = True
            raise ValueError('Not enough edges to initialize edge_sequence() object')

        self.cur_time = self.cur_states[0]

        if start_time is not None:
            init_step = start_time - self.cur_time
            if init_step > 0.0:
                self.advance(init_step)

        
    def advance(self, time_step=None):
        '''Move forward through edges by time_step amount. Uses default time_step from
        constructor if None is passed in here.
        '''
        if time_step == None:
            time_step = self.time_step
        
        self.cur_time += time_step
        while self.cur_time > self.next_states[0]:
            self.cur_states = self.next_states
            try:
                self.next_states = self.edges.next()
            except StopIteration:
                self.it_end = True
                break

    def advance_to_edge(self):
        '''Advance to the next edge after the current time in the sequence'''
        time_step = self.next_states[0] - self.cur_time
        self.cur_time = self.next_states[0]
        self.cur_states = self.next_states
        try:
            self.next_states = self.edges.next()
        except StopIteration:
            self.it_end = True
            return 0.0
            
        return time_step
    
    def cur_state(self):
        return self.cur_states[1]
    
    def at_end(self):
        return self.it_end
        
class frame_status(object):
    Ok = 0
    Warning = 100
    Error = 200
    
class frame(object):
    def __init__(self, bounds, data=None, name='unknown', status=frame_status.Ok):
        self.name = name
        self.start_time = bounds[0] # (start time, end time)
        self.end_time = bounds[1]
        self.data = data
        self.subframes = []
        self.events = [] # list of strings describing notable events during the frame
        self.status = status
        self.stream_id = 0 # associate this frame from multiplexed data with a particular stream

    def nested_status(self):
        cur_status = self.status
        for sf in self.subframes():
            ns = sf.nested_status()
            cur_status = ns if ns > cur_status else cur_status
            
        return cur_status

        
    def __repr__(self):
        return 'frame(({0},{1}), {2}, \'{3}\')'.format(self.start_time, self.end_time, \
            repr(self.data), self.name)
            

class serial_frame(frame):
    def __init__(self, bounds, data=None):
        frame.__init__(self, bounds, data)
        self.name = 'async. data'
        
    def __str__(self):
        return chr(self.data)


class decoder(object):
    pass
        
    
def serial_decode(samples, bits=8, parity=None, stop_bits=1, lsb_first=True, inverted=False, baud_rate=None, use_std_baud=True):

    # tee off an iterator to determine logic thresholds
    samp_it, thresh_it = itertools.tee(samples)
    
    logic = find_logic_levels(thresh_it, max_samples=5000)
    if logic is None:
        raise RuntimeError('Unable to find avg. logic levels of waveform')

    # tee off an independent iterator to determine baud rate
    edges_it, sre_it = itertools.tee(find_edges(samp_it, logic))
    
    # edges_it = list(edges_it)
    # print(time_axis[0])
    # print(edges_it[:10])
    # edges_it = iter(edges_it)
    
    
    if baud_rate is None:
        # Find the baud rate
        
        # Experiments on random data indicate that find_symbol_rate() will almost
        # always converge to a close estimate of baud rate within the first 35 edges.
        # It seems to be a guarantee after 50 edges.
        symbol_rate_edges = itertools.islice(sre_it, 50)
        
        # FIX: check number of edges retrieved and warn if not enough
        raw_symbol_rate = find_symbol_rate(symbol_rate_edges)
        print('## raw baud', raw_symbol_rate)
        
        # delete the tee'd iterators so that the internal buffer will not grow
        # as the edges_it is advanced later on
        del symbol_rate_edges
        del sre_it
        
        std_bauds = [110, 300, 600, 1200, 2400, 4800, 9600, 14400, 19200, 28800, 38400, 5600, 57600, 115200, \
            128000, 153600, 230400, 256000, 460800, 921600]

        if use_std_baud:
            baud_rate = min(std_bauds, key=lambda x: abs(x - raw_symbol_rate))
        else:
            baud_rate = raw_symbol_rate
    
    bit_period = 1.0 / float(baud_rate)
    es = edge_sequence(edges_it, bit_period)
    
    # Now we start the actual decode process
    
    if inverted:
        mark = 1
        space = 0
    else:
        mark = 0
        space = 1
        
    # initialize to point where state is 'mark' --> idle time before first start bit
    while es.cur_state() == space and not es.at_end():
        es.advance_to_edge()
        
    #print('start bit', es.cur_time)
    
    while not es.at_end():
        # look for start bit falling edge
        es.advance_to_edge()
        start_time = es.cur_time
        data_time = es.cur_time + bit_period
        es.advance(bit_period * 1.5) # move to middle of first data bit
        
        byte = 0
        cur_bit = 0
        while cur_bit < bits:
            bit_val = es.cur_state()
            if not inverted:
                bit_val = 1 - bit_val
            
            if lsb_first:
                byte = byte >> 1 | (bit_val << (bits-1))
            else:
                byte = byte << 1 | bit_val
                
            cur_bit += 1
            es.advance()
            #print(es.cur_time)
            
        data_end_time = es.cur_time - bit_period * 0.5
        if not parity is None:
            parity_time = data_end_time
            #FIX: check parity
            es.advance()
        
        stop_time = es.cur_time - bit_period * 0.5
        # FIX: verify stop bit
        
        end_time = es.cur_time + bit_period * (stop_bits - 0.5)
        
        # construct frame objects
        nf = serial_frame((start_time, end_time), byte)
        
        nf.subframes.append(frame((start_time, data_time), name='start bit'))
        nf.subframes.append(frame((data_time, data_end_time), byte, name='data bits'))
        if not parity is None:
            nf.subframe.append(frame((parity_time, stop_time), name='parity'))
            
        nf.subframes.append(frame((stop_time, end_time), name='stop bit'))
            
        #print(byte, bin(byte), chr(byte))
        yield nf
        
    #return frames