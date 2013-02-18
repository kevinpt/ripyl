#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Protocol decode library
   General routines shared between decoders
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

from __future__ import print_function, division

import numpy as np
import scipy as sp
import math
import itertools
import collections

from stats import OnlineStats
from streaming import *

import matplotlib.pyplot as plt

def find_bot_top_hist_peaks(samples, bins, use_kde=False):
    '''Find the bottom and top peaks in a histogram of data sample magnitudes.
    These are the left-most and right-most of the two largest peaks in the histogram.
    
    samples
        A sequence representing the population of data samples that will be
        analyzed for peaks
    
    bins
        The number of bins to use for the histogram

    use_kde
        Boolean indicating whether to construct the histogram from a Kernel Density
        Estimate. This is useful for approximating normally distributed peaks on
        synthetic data sets lacking noise.
        
    Returns a 2-tuple (bot, top) representing the bottom and top peaks. The value for
      each peak is the center of the histogram bin that represents the midpoint of the
      population for that peak.
    Returns None if less than two peaks are found in the histogram
    '''
    
    if not use_kde:
        hist, bin_edges = np.histogram(samples, bins=bins)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    else:
    
        kde = sp.stats.gaussian_kde(samples, bw_method=0.05)
        
        mxv = max(samples)
        mnv = min(samples)
        r = mxv - mnv
        # Expand the upper and lower bounds by 10% to allow room for gaussian tails at the extremes
        mnv -= r * 0.1
        mxv += r * 0.1
        
        step = (mxv - mnv) / bins
        bin_centers = np.arange(mnv, mxv, step)
        hist = 100 * kde(bin_centers)
        
    #plt.plot(bin_centers, hist)
    #plt.show()
    peaks = find_hist_peaks(hist)
    
    print('@@@@@@ len(peaks)', len(peaks), peaks)

    # make sure we have at least two peaks
    if len(peaks) < 2:
        return None
    
    # sort peaks by height
    heights = ((i, max(hist[p[0]:p[1]+1])) for i, p in enumerate(peaks))
    heights = sorted(heights, key=lambda t: t[1])
    # the last two are the highest
    high_peaks = (peaks[heights[-1][0]], peaks[heights[-2][0]])
    
    # get the center of each peak
    bot_top = []
    for p in high_peaks:
        hslice = hist[p[0]:p[1]+1] # the bins for this peak
        cs = np.cumsum(hslice)
        mid_pop = cs[-1] // 2
        
        # find the bin where we reach the population midpoint
        mid_ix = 0
        for i, s in enumerate(cs):
            if s >= mid_pop:
                mid_ix = i
                break
                
        #TODO: consider interpolating between two bins nearest to the float(mid_pop)
                
        # get the original bin center for this population midpoint
        bot_top.append(bin_centers[p[0] + mid_ix])

    return tuple(sorted(bot_top))

    
def find_hist_peaks(hist):
    '''Find all peaks in a histogram
    This uses a modification of the method employed by the "peaks" function in
    LeCroy digital oscilloscopes. The original algorithm is described in various manuals
    such as the 9300 WP03 manual or WavePro manual RevC 2002 (p16-14).
    
    This algorithm works well for real world data sets where the histogram peaks are
    normally distributed (i.e. there is some noise present in the data set).
    For synthetic waveforms lacking noise or any intermediate samples between discrete
    logic levels, the statistical measures used to determine the threshold for a peak
    are not valid. The threshold t2 ends up being too large and valid peaks may be
    excluded. To avoid this problem the histogram can be samples from a KDE instead.
    
    hist
        A sequence representing the histogram bin counts. Typically the first parameter
        returned by numpy.histogram() or a KDE from scipy.stats.gaussian_kde().
        
    Returns a list of peaks where each peak is a 2-tuple representing the
      start and end indices of the peak in hist.
    '''
    
    
    # get mean of all populated bins
    os = OnlineStats()
    for b in hist:
        if b > 0:
            os.accumulate(b)
            
    pop_mean = os.mean()
    
    t1 = pop_mean + 2.0 * math.sqrt(pop_mean)
    
    print('@@@@@ t1', t1, pop_mean)
    
    # find std. dev. of all bins under t1
    os.reset()
    for b in hist:
        if b > 0 and b < t1:
            os.accumulate(b)
        
    t2 = pop_mean + 2.0 * os.std(ddof=1)
    
    print('@@@@@ t2', t2, pop_mean, os.std(ddof=1))
    
    # plt.plot(hist)
    # plt.axhline(t1, color='k')
    # plt.axhline(t2, color='g')
    # plt.axhline(pop_mean, color='r')
    # plt.axhline(os.mean(), color='y')
    # plt.show()
    # plt.clf()
    
    # t2 is the threshold we will use to classify a bin as part of a peak
    # Essentially it is saying that a peak is any bin more than 2 std. devs.
    # above the mean. t1 was used to prevent the most extreme outliers from biasing
    # the std. dev.
    
    NEED_PEAK = 1
    IN_PEAK = 2
    
    state = NEED_PEAK
    peaks = []
    
    for i, b in enumerate(hist):
        if state == NEED_PEAK:
            if b >= t2:
                peak_start = i
                state = IN_PEAK
        
        elif state == IN_PEAK:
            if b < t2:
                peaks.append((peak_start, i))
                state = NEED_PEAK
                
    # if the last bin was the start of a peak then we add it as a special case
    if peak_start == len(hist)-1:
        peaks.append((peak_start, peak_start))
                
    merge_gap = len(hist) / 100.0
    suppress_gap = len(hist) / 50.0
    
    prev_end = 0
    merged = [0] * len(peaks)
    suppressed = [0] * len(peaks)
    
    
    for i, p in enumerate(peaks):
        s, e = p
        
        if i == 0:
            gap = 2.0 * suppress_gap # just a value big enough to ensure the first peak is preserved
        else:
            gap = s - prev_end
            
        if gap < merge_gap:
            # merge these two peaks
            peaks[i] = (peaks[i-1][0], e) # put the prev peak start in this one
            merged[i-1] = 1
            
        if gap >= merge_gap and gap < suppress_gap:
            # suppress this peak
            suppressed[i] = 1
        
    
        prev_end = e
    
    filtered_peaks = []
    for i, p in enumerate(peaks):
        if merged[i] == 0 and suppressed[i] == 0:
            filtered_peaks.append(p)
            
    return filtered_peaks
    
    

def find_logic_levels(samples, max_samples, buf_size):
    '''Automatically determine the logic levels of a digital signal.
    
    This function consumes up to max_samples from samples in an attempt
    to build a buffer containing a representative set of samples at high
    and low logic levels. Less than max_samples may be consumed if an edge
    is found and the remaining half of the buffer is filled before the
    max_samples threshold is reached.
    
    samples
        An iterable representing a sequence of samples. Each sample is a
        2-tuple representing the time of the sample and the sample's value.
        
    max_samples
        The maximum number of samples to consume from the samples iterable.
        
    buf_size
        The maximum size of the sample buffer to analyze for logic levels.
        This should be less than max_samples. 
        
    Returns a 2-tuple (low, high) representing the logic levels of the samples
    Returns None if less than two peaks are found in the sample histogram.
    '''

    # Get a minimal pool of samples containing both logic levels
    print('!!!!!! buf_size', buf_size)
    buf = collections.deque(maxlen=buf_size)
    os = OnlineStats()
    os_init = 0
    
    S_FIND_EDGE = 0
    S_FINISH_BUF = 1
    
    state = S_FIND_EDGE
    sc = 0
    while sc < max_samples:
        try:
            ns = next(samples)[1]
            buf.append(ns)
            sc += 1
            
            if state == S_FIND_EDGE:
                # build stats on the samples seen so far
                os.accumulate(ns)
                os_init += 1
                if os_init > 3 and abs(ns - os.mean()) > (3 * os.std()):
                    # The sample is more than 3 std. devs. from the mean
                    # This is likely an edge event
                    state = S_FINISH_BUF
                    if len(buf) < buf_size // 2:
                        buf_remaining = buf_size - len(buf)
                    else:
                        buf_remaining = buf_size // 2
                        
                    print('!!!!!!!!!! found edge', sc, buf_remaining)

            else: # S_FINISH_BUF
                # Accumulate samples until the edge event is in the middle of the
                # buffer or the buffer is filled
                #print('S_FINISH_BUF', buf_remaining, len(buf))
                buf_remaining -= 1
                if buf_remaining <= 0 and len(buf) >= buf_size:
                    print('!!!!!!!!! buf FILLED')
                    break

        except StopIteration:
            break

    print('$$$$$$$$ len(buf)', len(buf), sc)
    #plt.plot(buf)
    #plt.show()

    return find_bot_top_hist_peaks(buf, 100, use_kde=True)
        


def find_edges(samples, logic, hysteresis=0.4):
    '''Find the edges in a sampled digital waveform
    
    This is a generator function that can be used in a pipeline of waveform
    procesing operations.
    
    samples
        An iterable representing a sequence of samples. Each sample is a
        2-tuple representing the time of the sample and the sample's value.

    logic
        A 2-tuple (low, high) representing the mean logic levels in the sampled waveform
        
    hysteresis
        A value between 0.0 and 1.0 representing the amount of hysteresis the use for
        detecting valid edge crossings.
        
    Yields a series of 2-tuples (time, value) representing the time and
      logic value (0 or 1) for each edge transition. The first tuple
      yielded is the initial state of the sampled waveform. All remaining
      tuples are detected edges.
    
    
    '''
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
    start_time, initial_sample = next(samples) # FIX: wrap in try block
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
    
    
def find_symbol_rate(edges, sample_rate=1.0, spectra=4):
    '''Determine the base symbol rate from a set of edges
    
    This function depends on the edge data containing a variety of spans between
    edges all related to the fundamental symbol rate. The Harmonic Product Spectrum
    (HPS) of the edge span values is calculated and used to isolate the fundamental
    symbol rate. This function will not work properly on a clock signal containing
    a single time span between edges due to the lack of higher fundementals needed
    by the HPS unless spectra=1 which effectively disables the HPS operation.
    
    edges
        An iterable of 2-tuples representing each edge transition.
        The tuples are in one of two forms:
            * absolute time  (time, logic level)
            * sample indexed (index, logic level)
            
        This function will consume all elements of the edges iterable.
        It must have a finite length
        
    sample_rate
        An adjustment to convert the raw symbol rate from samples to time.
        If the edges parameter is based on absolute time units then this
        should remain the default value of 1.0.
        
    spectra
        The number of spectra to include in the calculation of the HPS. This
        number should not larger than the highest harmonic in the edge span
        data.
    
    Returns the estimated symbol rate of the edge data set as an int
    '''
    e = np.array(zip(*edges)[0]) # get the sample indices of each edge
    spans = e[1:] - e[:-1] # time span (in samples) between successive edges
    
    # generate kernel density estimate of span histogram
    kde = sp.stats.gaussian_kde(spans, bw_method=0.05)
    
    # Compute the harmonic product spectrum from the KDE
    # This should leave us with one strong peak for the span corresponding to the
    # fundamental symbol rate
    mv = max(spans) * 1.1 # leave some extra room for the rightmost peak of the KDE
    step = mv / 500
    xs = np.arange(0, mv, step)
    s = kde(xs) # fundamental spectrum
    
    # isolate the fundamental span width by multiplying downshifted spectra
    for i in xrange(2,spectra+1):
        s *= kde(np.arange(0, mv*i, step*i))[:len(s)]

    # largest peak from the HPS. This is approximately the length of one bit period
    peak_span = xs[np.argmax(s)]
    symbol_rate = int(sample_rate / peak_span)
    
    return symbol_rate
    

class EdgeSequence(object):
    '''Utility class to walk through an edge iterator in arbitrary time steps'''

    def __init__(self, edges, time_step, start_time=None):
        '''
            edges
                An iterable of 2-tuples representing each edge transition.
                The 2-tuples *must* be in the absolute time form (time, logic level).
            
            time_step
                The default time step for advance() when it is called
                without an argument.
            
            start_time
                The initial starting time for the sequence.
                
            Raises StreamError when there are less than two elements to the edges iterable
        '''
        self.edges = edges
        self.time_step = time_step
        self.it_end = False
        
        try:
            self.cur_states = next(self.edges)
            self.next_states = next(self.edges)
        except StopIteration:
            self.it_end = True
            raise StreamError('Not enough edges to initialize edge_sequence() object')

        self.cur_time = self.cur_states[0]

        if start_time is not None:
            init_step = start_time - self.cur_time
            if init_step > 0.0:
                self.advance(init_step)

        
    def advance(self, time_step=None):
        '''Move forward through edges by a given amount of time.
        
        time_step
            The amount of time to move forward. If None, the default
            time_step from the constructor is used.
        '''
        if time_step == None:
            time_step = self.time_step
        
        self.cur_time += time_step
        while self.cur_time > self.next_states[0]:
            self.cur_states = self.next_states
            try:
                self.next_states = next(self.edges)
            except StopIteration:
                self.it_end = True
                break

    def advance_to_edge(self):
        '''Advance to the next edge in the iterator after the current time
        
        Returns the amount of time advanced as a float.
        '''
        
        if self.it_end:
            return 0.0
            
        time_step = 0.0
        start_state = self.cur_states[1]
        while self.cur_states[1] == start_state:
            time_step += self.next_states[0] - self.cur_time
            self.cur_time = self.next_states[0]
            self.cur_states = self.next_states
            
            try:
                self.next_states = next(self.edges)
            except StopIteration:
                # flag end of sequence if the state remains the same (no final edge)
                if self.cur_states[1] == start_state:
                    self.it_end = True
                break
            
        return time_step
    
    def cur_state(self):
        '''The logic level of the edge iterator at the current time'''
        return self.cur_states[1]
    
    def at_end(self):
        '''Returns True when the edge iterator has terminated'''
        return self.it_end


class MultiEdgeSequence(object):
    '''Utility class to walk through a group of edge iterators in arbitrary time steps'''
    def __init__(self, edge_sets, time_step, start_time=None):
        '''
        edge_sets
            A dict of edge sequence iterators keyed by the string name of the channel
        
        time_step
            The default time step for advance() when it is called
            without an argument.
        
        start_time
            The initial starting time for the sequence.
        '''

        self.channel_names, self.edge_chans = zip(*edge_sets.items())
        self.sequences = [EdgeSequence(e, time_step, start_time) for e in self.edge_chans]
        
        self.channel_ids = {}
        
        for i, cid in enumerate(self.channel_names):
            self.channel_ids[cid] = i

    def advance(self, time_step=None):
        '''Move forward through edges by a given amount of time.
        
        time_step
            The amount of time to move forward. If None, the default
            time_step from the constructor is used.
        '''
        for s in self.sequences:
            s.advance(time_step)
            
    def advance_to_edge(self, channel_name=None):
        '''Advance to the next edge among the edge sets or in a named channel
        after the current time
        
        channel_name
            If None, the edge sets are advanced to the closest edge after the current
            time. if a valid channel name is provided the edge sets are advanced to
            the closest edge on that channel.
        
        Returns a tuple (time, channel_name) representing the amount of time advanced
          as a float and the name of the channel containing the edge. If there are no
          unterminated edge sequences then the tuple (0,0, '') is returned.
          
        Raises ValueError if channel_name is invalid
        '''
        # get the sequence for the channel
        if channel_name is None:
            # find the channel with the nearest edge after the current time
            # that hasn't ended
            active_seq = []
            for s in self.sequences:
                if not s.at_end():
                    active_seq.append(s)
                    
            if len(active_seq) > 0:
                edge_s = min(active_seq, key=lambda x: x.next_states[0])
                
                # find its channel id
                for k, v in self.channel_ids.iteritems():
                    if self.sequences[v] is edge_s:
                        channel_name = k
                        break
            else: # no active sequences left
                return (0.0, '')
        else:
            # check for channel_name in sets
            if channel_name in self.channel_ids.iterkeys():
                edge_s = self.sequences[self.channel_ids[channel_name]]
            else:
                raise ValueError("Invalid channel name '{0}'".format(channel_name))
        
        time_step = edge_s.advance_to_edge()
        
        # advance the other channels to the same time
        if time_step > 0.0:
            for s in self.sequences:
                if not s is edge_s:
                    s.advance(time_step)
                    
        return (time_step, channel_name)

    def cur_state(self, channel_name=None):
        '''Get the current state of the edge sets
        
        channel_name
            Name of the channel to retrieve state from
            
        Returns the value of the named channel's state. If channel_name is None
          the state of all channels is returned as a list.
          
        Raises ValueError if channel_name is invalid
        '''
    
        if channel_name is None:
            return [s.cur_state() for s in self.sequences]
        else:
            if channel_name in self.channel_ids.iterkeys():
                return self.sequences[self.channel_ids[channel_name]].cur_state()
            else:
                raise ValueError("Invalid channel name '{0}'".format(channel_name))
            
    def cur_time(self):
        '''Get the current time of the edge sets'''
        return self.sequences[0].cur_time

    def at_end(self, channel_name=None):
        '''Test if the sequences have ended
        
        channel_name
            The name of the channel to test for termination
            
        Returns True when the named edge iterator has terminated. If channel_name is
          None, returns True then all channels in the set have terminated.
          
        Raises ValueError if channel_name is invalid
        '''
        if channel_name is None:
            return all(s.at_end() for s in self.sequences)
        else:
            if channel_name in self.channel_ids.iterkeys():
                return self.sequences[self.channel_ids[channel_name]].at_end()
            else:
                raise ValueError("Invalid channel name '{0}'".format(channel_name))


class StreamStatus(object):
    '''Enumeration for standard stream status codes'''
    Ok = 0
    Warning = 100
    Error = 200
    
class StreamRecord(object):
    '''Base class for protocol decoder output stream objects'''
    def __init__(self, kind='unknown', status=StreamStatus.Ok):
        self.kind = kind
        self.status = status
        self.stream_id = 0 # associate this record from multiplexed data with a particular stream
        self.subrecords = []

    def nested_status(self):
        '''Retrieve the highest status value from this record and its subrecords'''
        cur_status = self.status
        for sf in self.subrecords:
            ns = sf.nested_status()
            cur_status = ns if ns > cur_status else cur_status
            
        return cur_status

    def __repr__(self):
        return 'StreamRecord(\'{0}\')'.format(self.kind)
    
class StreamSegment(StreamRecord):
    '''A stream element that spans two points in time'''
    def __init__(self, time_bounds, data=None, kind='unknown segment', status=StreamStatus.Ok):
        StreamRecord.__init__(self, kind, status)
        self.start_time = time_bounds[0] # (start time, end time)
        self.end_time = time_bounds[1]
        self.data = data
        
    def __repr__(self):
        return 'StreamSegment(({0},{1}), {2}, \'{3}\')'.format(self.start_time, self.end_time, \
            repr(self.data), self.kind)

class StreamEvent(StreamRecord):
    '''A stream element that occurs at a specific point in time'''
    def __init__(self, time, data=None, kind='unknown event', status=StreamStatus.Ok):
        StreamRecord.__init__(self, kind, status)
        self.time = time
        self.data = data

    def __repr__(self):
        return 'StreamEvent({0}, {1}, \'{2}\')'.format(self.time, \
            repr(self.data), self.kind)        

        
    
