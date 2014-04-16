#!/usr/bin/python
# -*- coding: utf-8 -*-

'''General routines shared between decoders
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

from __future__ import print_function, division

import numpy as np
import scipy as sp
import math
import collections
import itertools

import ripyl.util.stats as stats
from ripyl.streaming import ChunkExtractor, StreamError, AutoLevelError
from ripyl.util.equality import relatively_equal

#import matplotlib.pyplot as plt


def gen_histogram(raw_samples, bins, use_kde=False, kde_bw=0.05):
    '''Generate a histogram using either normal binning or a KDE
    
    raw_samples (sequence of numbers)
        A sequence representing the population of data samples that will be
        analyzed for peaks
    
    bins (int)
        The number of bins to use for the histogram

    use_kde (bool)
        Boolean indicating whether to construct the histogram from a Kernel Density
        Estimate. This is useful for approximating normally distributed peaks on
        synthetic data sets lacking noise.
        
    kde_bw (float)
        Float providing the bandwidth parameter for the KDE
    
    Returns a tuple (hist, bin_centers) containing lists of the histogram bins and
      the center value of each bin.

    Raises ValueError if a KDE cannot be constructed
    '''
    if not use_kde:
        hist, bin_edges = np.histogram(raw_samples, bins=bins)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    else:
    
        try:
            #print('#### len(raw_samples)', len(raw_samples))
            kde = sp.stats.gaussian_kde(raw_samples, bw_method=kde_bw)
        except np.linalg.linalg.LinAlgError:
            # If the sample data set contains constant samples, gaussian_kde()
            # will raise this exception.
            raise ValueError('Cannot construct KDE for histogram approximation. No sample variation present')
        
        mxv = max(raw_samples)
        mnv = min(raw_samples)
        r = mxv - mnv
        # Expand the upper and lower bounds by 10% to allow room for gaussian tails at the extremes
        mnv -= r * 0.1
        mxv += r * 0.1
        
        step = (mxv - mnv) / bins
        bin_centers = np.arange(mnv, mxv, step)
        hist = 1000 * kde(bin_centers)
        
    return hist, bin_centers


def find_bot_top_hist_peaks(raw_samples, bins, use_kde=False, kde_bw=0.05):
    '''Find the bottom and top peaks in a histogram of data sample magnitudes.
    These are the left-most and right-most of the two largest peaks in the histogram.
    
    raw_samples (sequence of numbers)
        A sequence representing the population of data samples that will be
        analyzed for peaks
    
    bins (int)
        The number of bins to use for the histogram

    use_kde (bool)
        Boolean indicating whether to construct the histogram from a Kernel Density
        Estimate. This is useful for approximating normally distributed peaks on
        synthetic data sets lacking noise.
        
    kde_bw (float)
        Float providing the bandwidth parameter for the KDE
        
    Returns a 2-tuple (bot, top) representing the bottom and top peaks. The value for
      each peak is the center of the histogram bin that represents the midpoint of the
      population for that peak.
    Returns None if less than two peaks are found in the histogram
    
    Raises ValueError if a KDE cannot be constructed
    '''

    hist, bin_centers = gen_histogram(raw_samples, bins, use_kde, kde_bw)
        
    #plt.plot(bin_centers, hist)
    #plt.show()
    peaks = find_hist_peaks(hist)

    if len(peaks) < 2:
        # In some cases where 1's or 0's are significantly dominant over the other
        # the histogram is too skewed and find_hist_peaks() sets a threshold too high.

        # Split the histogram and attempt to find peaks in each half to handle this case
        half = len(hist) // 2
        l_peaks = find_hist_peaks(hist[:half])
        r_peaks = find_hist_peaks(hist[half:])
        if len(l_peaks) >= 1 and len(r_peaks) >= 1:
            peaks = l_peaks
            peaks.extend((p[0] + half, p[1] + half) for p in r_peaks)
            #print('$$$$ peaks2:', peaks)
    
    # Make sure we have at least two peaks
    if len(peaks) < 2:
        return None


    # Take the lower and upper peaks from the list
    end_peaks = (peaks[0], peaks[-1])
    
    # get the center of each peak
    bot_top = []
    for p in end_peaks:
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

    
def find_hist_peaks(hist, thresh_scale=1.0):
    '''Find all peaks in a histogram
    This uses a modification of the method employed by the "peaks" function in
    LeCroy digital oscilloscopes. The original algorithm is described in various manuals
    such as the 9300 WP03 manual or WavePro manual RevC 2002 (p16-14).
    
    This algorithm works well for real world data sets where the histogram peaks are
    normally distributed (i.e. there is some noise present in the data set).
    For synthetic waveforms lacking noise or any intermediate samples between discrete
    logic levels, the statistical measures used to determine the threshold for a peak
    are not valid. The threshold t2 ends up being too large and valid peaks may be
    excluded. To avoid this problem the histogram can be sampled from a KDE instead or
    the thresh_scale parameter can be set to a lower value.
    
    hist (sequence of int)
        A sequence representing the histogram bin counts. Typically the first parameter
        returned by numpy.histogram() or a KDE from scipy.stats.gaussian_kde().

    thresh_scale (float)
        Apply a scale factor to the internal threshold for peak classification.
        
    Returns a list of peaks where each peak is a 2-tuple representing the
      start and end indices of the peak in hist.
    '''
    
    
    # get mean of all populated bins
    os = stats.OnlineStats()
    pop_bins = [b for b in hist if b > 0]
    os.accumulate_array(pop_bins)
            
    pop_mean = os.mean()
    
    t1 = pop_mean + 2.0 * math.sqrt(pop_mean)
    
    #print('@@@@@ t1', t1, pop_mean)
    
    # find std. dev. of all populated bins under t1
    os.reset()
    os.accumulate_array([b for b in pop_bins if b < t1])
        
    t2 = pop_mean + thresh_scale * 2.0 * os.std(ddof=1) # Lecroy uses 2*std but that can be unreliable
    
    #print('@@@@@ t2', t2, pop_mean, os.std(ddof=1))
    
    #plt.plot(hist)
    #plt.axhline(t1, color='k')
    #plt.axhline(t2, color='g')
    #plt.axhline(pop_mean, color='r')
    #plt.axhline(os.mean(), color='y')
    #plt.show()
    
    # t2 is the threshold we will use to classify a bin as part of a peak
    # Essentially it is saying that a peak is any bin more than 2 std. devs.
    # above the mean. t1 was used to prevent the most extreme outliers from biasing
    # the std. dev.
    
    NEED_PEAK = 1
    IN_PEAK = 2
    
    state = NEED_PEAK
    peaks = []
    peak_start = -1
    
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

   
    # look for peaks that are within the merge limit
    peak_gaps = [b[0] - a[1] for a, b in zip(peaks[0:-1], peaks[1:])]
    merged = [0] * len(peaks)
    for i, gap in enumerate(peak_gaps):
        if gap < merge_gap:
            # merge these two peaks
            peaks[i+1] = (peaks[i][0], peaks[i+1][1]) # put the prev peak start in this one
            merged[i] = 1

    merged_peaks = [p for i, p in enumerate(peaks) if merged[i] == 0]
    
    # look for peaks that are within the limit for suppression
    peak_gaps = [b[0] - a[1] for a, b in zip(merged_peaks[0:-1], merged_peaks[1:])]
    suppressed = [0] * len(merged_peaks)
    
    for i, gap in enumerate(peak_gaps):
        if gap < suppress_gap:
            # suppress the smallest of the two peaks
            ix_l = i
            ix_r = i+1
            width_l = merged_peaks[ix_l][1] - merged_peaks[ix_l][0]
            width_r = merged_peaks[ix_r][1] - merged_peaks[ix_r][0]
            
            if width_l > width_r: # left peak is bigger
                suppressed[ix_r] = 1
            else: # right peak is bigger
                suppressed[ix_l] = 1

    
    filtered_peaks = [p for i, p in enumerate(merged_peaks) if suppressed[i] == 0]
            
    return filtered_peaks
    
    

def find_logic_levels(samples, max_samples=20000, buf_size=2000):
    '''Automatically determine the binary logic levels of a digital signal.
    
    This function consumes up to max_samples from samples in an attempt
    to build a buffer containing a representative set of samples at high
    and low logic levels. Less than max_samples may be consumed if an edge
    is found and the remaining half of the buffer is filled before the
    max_samples threshold is reached.

    Warning: this function is insensitive to any edge transition that
    occurs within the first 100 samples. If the distribution of samples
    is heavily skewed toward one level over the other None may be returned.
    To be reliable, a set of samples should contain more than one edge or
    a solitary edge after the 400th sample.
    
    samples (iterable of SampleChunk objects)
        An iterable sample stream. Each element is a SampleChunk containing
        an array of samples.

    max_samples (int)
        The maximum number of samples to consume from the samples iterable.
        This should be at least 2x buf_size and will be coerced to that value
        if it is less.
        
    buf_size (int)
        The maximum size of the sample buffer to analyze for logic levels.
        This should be less than max_samples. 
        
    Returns a 2-tuple (low, high) representing the logic levels of the samples
    Returns None if less than two peaks are found in the sample histogram.

    '''

    # Get a minimal pool of samples containing both logic levels
    # We use a statistical measure to find a likely first edge to minimize
    # the chance that our buffer doesn't contain any edge transmissions.
    
    
    et_buf_size = buf_size // 10 # accumulate stats on 1/10 buf_size samples before edge search
    mvavg_size = 10
    noise_filt_size = 3
    
    S_FIND_EDGE = 0
    S_FINISH_BUF = 1
    
    state = S_FIND_EDGE
    sc = 0
    
    # Coerce max samples to ensure that an edge occuring toward the end of an initial
    # buf_size samples can be centered in the buffer.
    if max_samples < 2 * buf_size:
        max_samples = 2 * buf_size


    # Perform an initial analysis to determine the edge threshold of the samples
    samp_it, samp_dly_it, et_it = itertools.tee(samples, 3)
    
    et_cex = ChunkExtractor(et_it)
    et_samples = et_cex.next_samples(et_buf_size)


    # We will create two moving averages of this pool of data
    # The first has a short period (3 samples) meant to smooth out isolated spikes of
    # noise. The second (10 samples) creates a smoother waveform representing the
    # local median for the creation of the differences later.
    nf_mvavg_buf = collections.deque(maxlen=noise_filt_size) # noise filter
    noise_filtered = []
    et_mvavg_buf = collections.deque(maxlen=mvavg_size)
    et_mvavg = []
    for ns in et_samples:
        nf_mvavg_buf.append(ns)
        noise_filtered.append(sum(nf_mvavg_buf) / len(nf_mvavg_buf)) # calculate moving avg.
        et_mvavg_buf.append(ns)
        et_mvavg.append(sum(et_mvavg_buf) / len(et_mvavg_buf)) # calculate moving avg.

    # The magnitude difference between the samples and their moving average indicates where
    # steady state samples are and where edge transitions are. 
    mvavg_diff = [abs(x - y) for x, y in zip(noise_filtered, et_mvavg)]

    # The "noise" difference is the same as above but with the moving average delay removed.
    # This minimizes the peaks from edge transitions and is more representative of the noise level
    # in the signal.
    noise_diff = [abs(x - y) for x, y in zip(noise_filtered, et_mvavg[(mvavg_size//2)-1:])]
    noise_threshold = max(noise_diff) * 1.5
    
    # The noise threshold gives us a simple test for the presence of edges in the initial
    # pool of data. This will guide our determination of the edge threshold for filling the
    # edge detection buffer.
    edges_present = True if max(mvavg_diff) > noise_threshold else False

    # NOTE: This test for edges present will not work reliably for slowly changing edges
    # (highly oversampled) especially when the SNR is low (<20dB). This should not pose an issue
    # as in this case the edge_threshold (set with 5x multiplier instead of 0.6x) will stay low
    # enough to permit edge detection in the next stage.

    # The test for edges present will also fail when the initial samples are a periodic signal
    # with a short period relative to the sample rate. To cover this case we compute an
    # auto-correlation and look for more than one peak indicating the presence of periodicity.
    acorr_edges_present = False
    if not edges_present:
        norm_noise_filt = noise_filtered - np.mean(noise_filtered)
        auto_corr = np.correlate(norm_noise_filt, norm_noise_filt, 'same')

        ac_max = np.max(auto_corr)
        if ac_max > 0.0:
            # Take the right half of the auto-correlation and normalize to 1000.0
            norm_ac = auto_corr[len(auto_corr)//2:] / ac_max * 1000.0
            ac_peaks = find_hist_peaks(norm_ac, thresh_scale=1.0)
            if len(ac_peaks) > 1:
                p1_max = np.max(norm_ac[ac_peaks[1][0]:ac_peaks[1][1]+1])
                #print('$$$ p1 max:', p1_max)
                if p1_max > 500.0:
                    acorr_edges_present = True

        #print('\n$$$ auto-correlation peaks:', ac_peaks, acorr_edges_present)

        #plt.plot(et_samples)
        #plt.plot(norm_ac)
        #plt.show()


    #rev_mvavg = [(x - y) for x, y in zip(et_mvavg, reversed(et_mvavg))]
    #os = OnlineStats()
    #os.accumulate(rev_mvavg)
    #rev_mvavg = [abs(x - os.mean()) for x in rev_mvavg]

    if edges_present or acorr_edges_present:
        #edge_threshold = max(mad2) * 0.75
        edge_threshold = max(mvavg_diff) * 0.6
    else:
        # Just noise
        #edge_threshold = max(mad2) * 10
        edge_threshold = max(mvavg_diff) * 5

    #print('$$$ edges present:', edges_present, acorr_edges_present, edge_threshold)

	# For synthetic waveforms with no noise present and no edges in the initial samples we will
	# get an edge_threshold of 0.0. In this case we will just set the threshold high enough to
	# detect a deviation from 0.0 for any reasonable real world input

    edge_threshold = max(edge_threshold, 1.0e-9)
        
    
    #print('### noise, edge threshold:', noise_threshold, edge_threshold, edges_present)
    
    del et_it
    
    # We have established the edge threshold. We will now construct the moving avg. difference
    # again. This time, any difference above the threshold will be an indicator of an edge
    # transition.

    if acorr_edges_present:
        samp_cex = ChunkExtractor(samp_it)
        buf = samp_cex.next_samples(buf_size)
        state = S_FINISH_BUF
    else:
    
        mvavg_buf = collections.deque(maxlen=mvavg_size)
        mvavg_dly_buf = collections.deque(maxlen=mvavg_size)
        buf = collections.deque(maxlen=buf_size)

        # skip initial samples to create disparity between samp_cex and dly_cex
        samp_cex = ChunkExtractor(samp_it)
        dly_cex = ChunkExtractor(samp_dly_it)
        delay_samples = 100
        samp_cex.next_samples(delay_samples)

        end_loop = False
        while True:
            cur_samp = samp_cex.next_samples()
            cur_dly_samp = dly_cex.next_samples()

            if cur_samp is None:
                break
        
            for i in xrange(len(cur_samp)):
            
                ns = cur_samp[i]
                sc += 1
                
                buf.append(ns)
                
                if state == S_FIND_EDGE:
                    if sc > (max_samples - buf_size):
                        end_loop = True
                        break

                    mvavg_buf.append(ns)
                    mvavg = sum(mvavg_buf) / len(mvavg_buf)  # calculate moving avg.
                    mvavg_dly_buf.append(cur_dly_samp[i])
                    mvavg_dly = sum(mvavg_dly_buf) / len(mvavg_dly_buf)  # calculate moving avg.
                    if abs(mvavg_dly - mvavg) > edge_threshold:
                        # This is likely an edge event
                        state = S_FINISH_BUF
                        if len(buf) < buf_size // 2:
                            buf_remaining = buf_size - len(buf)
                        else:
                            buf_remaining = buf_size // 2
                            
                        #print('##### Found edge {} {}'.format(len(buf), sc))
                    

                else: # S_FINISH_BUF
                    # Accumulate samples until the edge event is in the middle of the
                    # buffer or the buffer is filled
                    buf_remaining -= 1
                    if buf_remaining <= 0 and len(buf) >= buf_size:
                        end_loop = True
                        break

            if end_loop:
                break
            

    #plt.plot(et_samples)
    #plt.plot(et_mvavg)
    #plt.plot(noise_filtered)
    #plt.plot(mvavg_diff)
    #plt.plot(noise_diff)
    #plt.plot(rev_mvavg)
    #plt.axhline(noise_threshold, color='r')
    #plt.axhline(edge_threshold, color='g')
    #plt.plot(buf)
    #plt.show()
    
    # If we didn't see any edges in the buffered sample data then abort
    # before the histogram analysis
    if state != S_FINISH_BUF:
        return None

    try:
        logic_levels = find_bot_top_hist_peaks(buf, 100, use_kde=True)
        #print('### ll:', logic_levels, min(buf), max(buf))
    except ValueError:
        logic_levels = None


    #print('%%% logic_levels', logic_levels)

    return logic_levels



def check_logic_levels(samples, max_samples=20000, buf_size=2000):
    '''Automatically determine the binary logic levels of a digital signal.

    This is a wrapper for find_logic_levels() that handles teeing off
    a buffered sample stream and raising AutoLevelError when detection
    fails.

    samples (iterable of SampleChunk objects)
        An iterable sample stream. Each element is a SampleChunk containing
        an array of samples. This iterator is internally tee'd and becomes
        invalidated for further use. The return value includes a new sample
        stream to retrieve samples from.

    max_samples (int)
        The maximum number of samples to consume from the samples iterable.
        This should be at least 2x buf_size and will be coerced to that value
        if it is less.
        
    buf_size (int)
        The maximum size of the sample buffer to analyze for logic levels.
        This should be less than max_samples. 
    
    Returns a 2-tuple (sample steam, logic_levels) representing the buffered sample
      stream and a tuple of the detected logic levels of the samples.

    Raises AutoLevelError if less than two peaks are found in the sample histogram.
    '''

    # tee off an iterator to determine logic thresholds
    samp_it, thresh_it = itertools.tee(samples)
    
    logic_levels = find_logic_levels(thresh_it, max_samples, buf_size)
    del thresh_it

    if logic_levels is None:
        raise AutoLevelError

    return samp_it, logic_levels


def find_edges(samples, logic, hysteresis=0.4):
    '''Find the edges in a sampled digital waveform
    
    This is a generator function that can be used in a pipeline of waveform
    procesing operations.
    
    samples (iterable of SampleChunk objects)
        An iterable sample stream. Each element is a SampleChunk containing
        an array of samples.

    logic ((float, float))
        A 2-tuple (low, high) representing the mean logic levels in the sampled waveform
        
    hysteresis (float)
        A value between 0.0 and 1.0 representing the amount of hysteresis the use for
        detecting valid edge crossings.
        
    Yields a series of 2-tuples (time, value) representing the time and
      logic value (0 or 1) for each edge transition. The first tuple
      yielded is the initial state of the sampled waveform. All remaining
      tuples are detected edges.
      
    Raises StreamError if the stream is empty
    '''
    span = logic[1] - logic[0]
    thresh = (logic[1] + logic[0]) / 2.0
    hyst_top = span * (0.5 + hysteresis / 2.0) + logic[0]
    hyst_bot = span * (0.5 - hysteresis / 2.0) + logic[0]

    
    # A sample can be in one of three zones: two logic states (1, 0) and
    # one transition bands for the hysteresis
    
    ZONE_1_L1 = 1 # logic 1
    ZONE_2_T  = 2 # transition
    ZONE_3_L0 = 3 # logic 0
    
    def get_sample_zone(sample):
        if sample > hyst_top:
            zone = ZONE_1_L1
        elif sample > hyst_bot:
            zone = ZONE_2_T
        else:
            zone = ZONE_3_L0
            
        return zone
        
    def is_stable_zone(zone):
        return zone == ZONE_1_L1 or zone == ZONE_3_L0
        
    def zone_to_logic_state(zone):
        ls = 999
        if zone == ZONE_1_L1: ls = 1
        elif zone == ZONE_3_L0: ls = 0
        
        return ls
    
    
    # states
    ES_START = 0
    
    state = ES_START
    
    for sc in samples:
        t = sc.start_time
        sample_period = sc.sample_period
        chunk = sc.samples

        if state == ES_START: # set initial edge state
            initial_state = (t, 1 if chunk[0] > thresh else 0)
            yield initial_state

        for sample in chunk:

            zone = get_sample_zone(sample)
            
            if state == ES_START:
                # Stay in start until we reach one of the stable states
                if is_stable_zone(zone):
                    state = zone

            # last zone was a stable state
            elif state == ZONE_1_L1 or state == ZONE_3_L0:
                if is_stable_zone(zone):
                    if zone != state:
                        state = zone
                        yield (t, zone_to_logic_state(zone))
                else:
                    prev_stable = state
                    state = zone
            
            # last zone was a transitional state (in hysteresis band)
            elif state == ZONE_2_T:
                if is_stable_zone(zone):
                    if zone != prev_stable: # This wasn't just noise
                        yield (t, zone_to_logic_state(zone))

                state = zone

            t += sample_period


def expand_logic_levels(logic_levels, count):
    '''Generate evenly spaced logic levels

    logic_levels ((float, float))
        A 2-tuple (low, high) representing the min and max logic level to expand on

    count (int)
        The number of logic levels in the result. If the value is less than 3, the
        result is the same as the sequence passed as logic_levels.
    
    Returns a list of logic levels with count length representing each logic level
      evenly spaced between logic_levels[0] and logic_levels[1].
    '''

    if count >= 3:
        step = (logic_levels[1] - logic_levels[0]) / (count - 1)

        return [logic_levels[0]] + [logic_levels[0] + i * step for i in xrange(1, count-1)] + [logic_levels[1]]
    else:
        return logic_levels


def gen_hyst_thresholds(logic_levels, expand=None, hysteresis=0.1):
    '''Generate hysteresis thresholds for find_multi_edges()

    This function computes the hysteresis thresholds for multi-level edge finding
    with find_multi_edges().

    logic_levels (sequence of float)
        A sequence of the nominal voltage levels for each logic state sorted
        in ascending order or the (low, high) pair when expansion is used.

    expand (int or None)
        When not None, the number of logic levels to expand the provided logic_levels into.

    hysteresis (float)
        A value between 0.0 and 1.0 representing the amount of hysteresis the use for
        detecting valid edge crossings.

    Returns a list of floats. Every pair of numbers represents a hysteresis band.
    '''

    if expand:
        assert len(logic_levels) == 2, 'Expansion requires exactly two logic levels.'
        logic_levels = expand_logic_levels(logic_levels, expand)

    assert len(logic_levels) >= 2, 'There must be at least two logic levels'
    centers = []
    for a, b in zip(logic_levels[0:-1], logic_levels[1:]):
        centers.append((a + b) / 2.0)

    hyst = []
    hysteresis = min(max(hysteresis, 0.0), 1.0) # Coerce to range [0.0, 1.0]
    for level, c in zip(logic_levels[0:-1], centers):
        h_top = (c - level) * (1 + hysteresis) + level
        h_bot = (c - level) * (1 - hysteresis) + level
        
        hyst.extend((h_bot, h_top))

    return hyst


def find_multi_edges(samples, hyst_thresholds):
    '''Find the multi-level edges in a sampled digital waveform
    
    This is a generator function that can be used in a pipeline of waveform
    procesing operations.
    
    Note that the output of this function cannot be used directly without further
    processing. Transitions across multiple states cannot be easily
    distinguished from transitions incliding intermediate states.
    For the case of three states (-1, 0, 1), Short periods in the 0 state
    should be removed but this requires knowledge of the minimum time for a 0 state
    to be valid. This is performed by the remove_transitional_states() function.

    The logic state encoding is formulated to balance the number of positive and negative
    states around 0 for odd numbers of states and with one extra positive state for even
    state numbers. For 2 states the encoding is the usual (0,1). For 3: (-1, 0, 1).
    For 4: (-1, 0, 1, 2). For 5: (-2, -1, 0, 1, 2), etc. 
    
    samples (iterable of SampleChunk objects)
        An iterable sample stream. Each element is a SampleChunk containing
        an array of samples.

    hyst_thresholds (sequence of float)
        A sequence containing the hysteresis thresholds for the logic states.
        For N states there should be (N-1) * 2 thresholds.
        The gen_hyst_thresholds() function can compute these values from more
        usual logic parameters. The numbers must be sorted in ascending order.
        Every pair of numbers in the sequence forms the bounds of a hysteresis
        band. Samples within these bands are considered transient states. Samples
        outside these bands are the valid logic states.

    Yields a series of 2-tuples (time, int) representing the time and
      logic value for each edge transition. The first tuple
      yielded is the initial state of the sampled waveform. All remaining
      tuples are detected edges.
    
    Raises StreamError if the stream is empty
    '''


    assert len(hyst_thresholds) % 2 == 0, 'There must be an even number of hyst_thresholds'

    # To establish the initial state we need to compare the first sample against thresholds
    # without involving any hysteresis. We compute new thresholds at the center of each
    # hysteresis pair.
    center_thresholds = []
    for i in xrange(0, len(hyst_thresholds), 2):
        center_thresholds.append((hyst_thresholds[i] + hyst_thresholds[i+1]) / 2.0)

    def get_sample_zone(sample):
        for i in xrange(len(hyst_thresholds)):
            if sample <= hyst_thresholds[i]:
                return i

        # The sample is greater than the highest threshold
        return len(hyst_thresholds)
        
    def is_stable_zone(zone):
        return zone % 2 == 0 # Even zones are stable

    # Compute offset between zone codings and the final logic state coding
    # logic state = zone // 2 - zone_offset
    zone_offset = len(hyst_thresholds) // 4
    #print('### zone offset:', zone_offset, len(hyst_thresholds), hyst_thresholds, center_thresholds)
    def zone_to_logic_state(zone):
        if zone % 2 == 1: # Odd zones are in hysteresis transition bands
            return 999

        return zone // 2 - zone_offset
    
    # states
    ES_START = 1000
    # NOTE: The remaining states have the same encoding as the zone numbers.
    # These are integers starting from 0. Even zones represent stable states
    # corresponding to the logic levels we want to detect. Odd zones represent
    # unstable states corresponding to samples within the hysteresis transition bands.

    state = ES_START
    for sc in samples:
        t = sc.start_time
        #sample_period = sc.sample_period
        #chunk = sc.samples

        if state == ES_START: # Set initial edge state
            #initial_state = (t, 1 if chunk[0] > thresh_high else 0 if chunk[0] > thresh_low else -1)
            center_ix = len(center_thresholds)
            for i in xrange(center_ix):
                if sc.samples[0] <= center_thresholds[i]:
                    center_ix = i
                    break

            initial_state = (t, center_ix - zone_offset)
            yield initial_state

        for sample in sc.samples:
            #zone = get_sample_zone(sample)
            #zone_is_stable = is_stable_zone(zone)
            zone = len(hyst_thresholds)
            for i in xrange(len(hyst_thresholds)):
                if sample <= hyst_thresholds[i]:
                    zone = i
                    break
            zone_is_stable = zone % 2 == 0
            
            if state == ES_START:
                # Stay in start until we reach one of the stable states
                if zone_is_stable:
                    state = zone

            else:
                if state % 2 == 0: # last zone was a stable state
                    if zone_is_stable:
                        if zone != state:
                            state = zone
                            yield (t, zone // 2 - zone_offset) #zone_to_logic_state(zone))
                    else:
                        prev_stable = state
                        state = zone
                
                else: # last zone was a transitional state (in hysteresis band)
                    if zone_is_stable:
                        if zone != prev_stable: # This wasn't just noise
                            yield (t, zone // 2 - zone_offset) #zone_to_logic_state(zone))

                    state = zone

            t += sc.sample_period



def remove_transitional_states(edges, min_state_period):
    '''Filter out brief transitional states from an edge stream
    
    This is a generator function that can be used in a pipeline of waveform
    procesing operations.
    
    edges (iterable of (float, int) tuples)
        An iterable of 2-tuples representing each edge transition.
        The 2-tuples *must* be in the absolute time form (time, logic level).
    
    min_state_period (float)
        The threshold for transitional states. A transition lasting less than this
        threshold will be filtered out of the edge stream.

    Yields a series of 2-tuples (time, value) representing the time and
      logic value for each edge transition. The first tuple yielded is the
      initial state of the sampled waveform. All remaining tuples are
      detected edges.
      
    Raises StreamError if the stream is empty
    '''

    # Get the first edge
    try:
        prev_edge = next(edges)
    except StopIteration:
        raise StreamError('Unable to initialize edge stream')

    in_transition = False
    tran_start = None

    for edge in edges:
        ts = edge[0] - prev_edge[0]
        if in_transition:
            ts += prev_edge[0] - tran_start[0] # Include current transition in time step

        if ts >= min_state_period:
            if in_transition:
                # Merge edges
                merge_edge = ((tran_start[0] + prev_edge[0]) / 2, prev_edge[1])
                yield merge_edge
                in_transition = False
            else: 
                yield prev_edge

        elif not in_transition: # Start of a transition
            in_transition = True
            tran_start = prev_edge

        prev_edge = edge
    
    yield prev_edge # Last edge


    
def find_symbol_rate(edges, sample_rate=1.0, spectra=2, auto_span_limit=True, max_span_limit=None):
    '''Determine the base symbol rate from a set of edges

    This function depends on the edge data containing a variety of spans between
    edges all related to the fundamental symbol rate. The Harmonic Product Spectrum
    (HPS) of the edge span values is calculated and used to isolate the fundamental
    symbol rate. This function will not work properly on a clock signal containing
    a single time span between edges due to the lack of higher fundementals needed
    by the HPS unless spectra=1 which effectively disables the HPS operation.

    edges ([(float, int)...] or [(int, int)...])
        An iterable of 2-tuples representing each edge transition.
        The tuples are in one of two forms:
          * absolute time  (time, logic level)
          * sample indexed (index, logic level)

        This function will consume all elements of the edges iterable.
        It must have a finite length
        
    sample_rate (float)
        An adjustment to convert the raw symbol rate from samples to time.
        If the edges parameter is based on absolute time units then this
        should remain the default value of 1.0.
        
    spectra (int)
        The number of spectra to include in the calculation of the HPS. This
        number should not larger than the highest harmonic in the edge span
        data.
        
    auto_span_limit (bool)
        Excessively long edge spans can impair the symbol rate detection by
        reducing the resolution of the HPS. They are typically the result of
        long idle periods between the interesting parts we want to estimate
        the symbol rate from. When this parameter is True, an attempt is made
        to find the ideal limit for the spans included in the HPS.
        
    max_span_limit (int)
        An optional upper limit for span length to include in the HPS.
        auto_span_limit must be False for this to take effect.

   
    Returns the estimated symbol rate of the edge data set as an int
    
    Raises ValueError if there are not enough edge spans to evaluate
      a HPS.
    '''
    e = zip(*edges)
    e2 = np.array(e[0][1:]) # Get the sample indices of each edge after the first one
    spans = e2[1:] - e2[:-1] # Time span (in samples) between successive edges

    #plt.plot(e[0], e[1])
    #plt.show()

    if auto_span_limit:
        # Automatically find maximum span limit
        # The bw_method parameter is set to smear all small peaks together so
        # that the first peak of the KDE covers the most relevant parts to
        # measure the symbol rate from.
        
        mv = max(spans) * 1.1 # leave some extra room for the rightmost peak of the KDE
        bins = 1000
        step = mv / bins
        x_hps = np.arange(0, mv, step)[:bins]
        
        if len(spans) == 0:
            raise ValueError('Insufficient spans in edge set')
        
        kde = sp.stats.gaussian_kde(spans, bw_method=0.8)
        asl = kde(x_hps)[:bins]
        
        # Get the width of the first peak
        peaks = find_hist_peaks(asl)
        if len(peaks) >= 1:
            max_span_limit = x_hps[peaks[0][1]] * 2 # set limit to 2x the right edge of the peak

    if max_span_limit is not None:
        spans = [s for s in spans if s < max_span_limit]
        
    if len(spans) == 0:
        raise ValueError('Insufficient spans in edge set')


    mv = max(spans) * 1.1 # leave some extra room for the rightmost peak of the KDE
    bins = 1000
    step = mv / bins
    x_hps = np.arange(0, mv, step)[:bins]
        
    # generate kernel density estimate of span histogram
    kde = sp.stats.gaussian_kde(spans, bw_method=0.02)
    
    # Compute the harmonic product spectrum from the KDE
    # This should leave us with one strong peak for the span corresponding to the
    # fundamental symbol rate.
    hps = kde(x_hps)[:bins] # fundamental spectrum (slice needed because sometimes kde() returns bins+1 elements)

    # Find all peaks in the fundamental spectrum
    all_peaks = find_hist_peaks(hps)
    hps_pairs = zip(x_hps, hps)
    all_peak_spans = [max(hps_pairs[pk[0]:pk[1]+1], key=lambda x: x[1])[0] for pk in all_peaks]
    #print('$$$ all peak spans:', all_peak_spans)


    #plt.plot(x_hps, hps / hps[np.argmax(hps)])
    #print('$$$ hps peak:', max(hps))
    tallest_initial_peak = max(hps)
    
    # isolate the fundamental span width by multiplying downshifted spectra
    for i in xrange(2, spectra+1):
        hps *= kde(np.arange(0, mv*i, step*i))[:len(hps)]
        #k = kde(np.arange(0, mv*i, step*i))[:len(hps)]
        #plt.plot(x_hps, k / k[np.argmax(k)])
        #print('$$$ k peak:', max(k))
        #hps *= k

    #print('$$$ hps peak:', max(hps))
    #plt.plot(x_hps, hps / hps[np.argmax(hps)])
    #plt.show()

    # It is possible to get anomalous HPS peaks with extremely small values.
    # If the tallest peak in the final HPS isn't within three orders of magnitude
    # we will consider the HPS invalid.
    if max(hps) < tallest_initial_peak / 1000.0:
        return 0

    peaks = find_hist_peaks(hps)

    if len(peaks) < 1:
        return 0
    
    # We want the leftmost (first) peak of the HPS as the fundamental
    # This should be approximately the length of one bit period
    hps_pairs = zip(x_hps, hps)
    peak_span = max(hps_pairs[peaks[0][0]:peaks[0][1]+1], key=lambda x: x[1])[0]

    
    if peak_span != 0.0:
        # In cases where the 2nd harmonic is missing but the 3rd and 6th are present
        # we can miss the true fundamental span in the HPS.
        # Check if there was a peak span in the pre-HPS spectrum that is 1/3 of this peak.
        # If so then this peak is not likely the true fundamental.
        for pk in all_peak_spans:
            if relatively_equal(pk, peak_span / 3, 0.01):
                #print('$$$ MISSED harmonic', pk, peak_span)
                return 0

        symbol_rate = int(sample_rate / peak_span)
    else:
        symbol_rate = 0
    
    return symbol_rate
    
#FIX: clean up use of cur_time, cur_state, cur_state(), next_states, etc.
class EdgeSequence(object):
    '''Utility class to walk through an edge iterator in arbitrary time steps'''

    def __init__(self, edges, time_step, start_time=None):
        '''
        edges (sequence of (float, int) tuples)
            An iterable of 2-tuples representing each edge transition.
            The 2-tuples *must* be in the absolute time form (time, logic level).
        
        time_step (float)
            The default time step for advance() when it is called
            without an argument.
        
        start_time (float)
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
        
        time_step (float)
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
            
        start_state = self.cur_states[1]
        while self.cur_states[1] == start_state:
            self.cur_states = self.next_states
            
            try:
                self.next_states = next(self.edges)
            except StopIteration:
                # flag end of sequence if the state remains the same (no final edge)
                if self.cur_states[1] == start_state:
                    self.it_end = True
                break

        time_step = self.cur_states[0] - self.cur_time
        self.cur_time = self.cur_states[0]
            
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
        edge_sets (dict)
            A dict of edge sequence iterators keyed by the string name of the channel
        
        time_step (float)
            The default time step for advance() when it is called
            without an argument.
        
        start_time (float)
            The initial starting time for the sequence.
        '''

        self.channel_names, self.edge_chans = zip(*edge_sets.items())
        self.sequences = [EdgeSequence(e, time_step, start_time) for e in self.edge_chans]
        
        self.channel_ids = {}
        
        for i, cid in enumerate(self.channel_names):
            self.channel_ids[cid] = i

    def advance(self, time_step=None):
        '''Move forward through edges by a given amount of time.
        
        time_step (float)
            The amount of time to move forward. If None, the default
            time_step from the constructor is used.
        '''
        for s in self.sequences:
            s.advance(time_step)
            
    def advance_to_edge(self, channel_name=None):
        '''Advance to the next edge among the edge sets or in a named channel
        after the current time
        
        channel_name (string)
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
        
        channel_name (string)
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
        
        channel_name (string)
            The name of the channel to test for termination
            
        Returns True when the named edge iterator has terminated. If channel_name is
          None, returns True when all channels in the set have terminated.
          
        Raises ValueError if channel_name is invalid
        '''
        if channel_name is None:
            return all(s.at_end() for s in self.sequences)
        else:
            if channel_name in self.channel_ids.iterkeys():
                return self.sequences[self.channel_ids[channel_name]].at_end()
            else:
                raise ValueError("Invalid channel name '{0}'".format(channel_name))


