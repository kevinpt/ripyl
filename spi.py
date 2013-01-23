#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Protocol decode library
   SPI protocol decoder
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

from decode import *

class SpiFrame(StreamSegment):
    def __init__(self, bounds, data=None):
        StreamSegment.__init__(self, bounds, data)
        self.kind = 'SPI frame'
        
    def __str__(self):
        return str(self.data)

def spi_decode_2(clk, mosi, cs=None, cpol=0, cpha=0, lsb_first=True, stream_type=StreamType.Samples):
    if stream_type == StreamType.Samples:
        # tee off an iterator to determine logic thresholds
        s_clk_it, thresh_it = itertools.tee(clk)
        
        logic = find_logic_levels(thresh_it, max_samples=5000)
        if logic is None:
            raise StreamError('Unable to find avg. logic levels of waveform')
        del thresh_it
        
        hyst = 0.4
        clk_it = find_edges(s_clk_it, logic, hysteresis=hyst)
        mosi_it = find_edges(mosi, logic, hysteresis=hyst)
        if not cs is None:
            cs_it = find_edges(cs, logic, hysteresis=hyst)
        else:
            cs_it = None
    else: # the streams are already lists of edges
        clk_it = clk
        mosi_it = mosi
        cs_it = cs


    edge_sets = {
        'clk': clk_it,
        'mosi': mosi_it
    }
    
    if not cs_it is None:
        edge_sets['cs'] = cs_it
    
    es = MultiEdgeSequence(edge_sets, 0.0)
    
    if cpha == 0:
        active_edge = 1 if cpol == 0 else 0
    else:
        active_edge = 0 if cpol == 0 else 1
    
    step = -1 if lsb_first else 1
    
    bits = []
    start_time = None
    end_time = None
    prev_edge = None
    prev_cycle = None
    
    # begin to decode
    
    while not es.at_end():
        #start_time = es.cur_time()
        
        ctb = es.cur_time()
        
        ts, cname = es.advance_to_edge()
        
        # if ts == 0.0:
            # print('>>>', ts, cname)
            # break
            
        print(' ## ts={0}, {1}, ctb={2}, cts={3}'.format(ts, cname, ctb, es.cur_time()))
        
        if cname == 'cs' and not es.at_end('cs'):
            #print('CS event')
            print('    CS **', es.cur_time())
            pass # FIX: generate CS event
            
        elif cname == 'clk' and not es.at_end('clk'):
            clk_val = es.cur_state('clk')
            
            if clk_val == active_edge: # capture data bit
                print('    **', es.cur_time())
                # Check if the elapsed time is more than any previous cycle
                # This indicates that a previous word was complete
                if not prev_cycle is None and es.cur_time() - prev_edge > 1.05 * prev_cycle:
                    word = 0
                    for b in bits[::step]:
                        word = word << 1 | b
                    
                    nf = SpiFrame((start_time, end_time), word)
                    nf.word_size = len(bits)
                    
                    bits = []
                    start_time = None
                    
                    yield nf
                    
                # accumulate the bit
                if start_time is None:
                    start_time = es.cur_time()
                    
                bits.append(es.cur_state('mosi'))
                end_time = es.cur_time()
                #print('>> et', end_time, bits)
                
                if not prev_edge is None:
                    prev_cycle = es.cur_time() - prev_edge

                prev_edge = es.cur_time()
                
        
    if len(bits) > 0:
        word = 0
        for b in bits[::step]:
            word = word << 1 | b
        
        nf = SpiFrame((start_time, end_time), word)
        nf.word_size = len(bits)
        
        yield nf


    
        
def spi_decode(clk, mosi, cs, cpol=0, cpha=0):
    edge_sets = {
        'clk': clk,
        'mosi': mosi,
        'cs': cs
    }
    
    es = multi_edge_sequence(edge_sets, 0.0)
    
    prev_ts, _ = es.advance_to_edge('clk') # move to first edge of clock
    
    if cpha == 1:
        es.advance_to_edge('clk')
    
    end_decode = False
    #w_num = 0
    while not es.at_end():
        #if cpha == 1: # skip first edge of clock
        #    ts = es.advance_to_edge('clk')
        #    if ts == 0.0:
        #        break
        
        start_time = es.cur_time()
        start_cs = es.cur_state('cs')
        
        #b_num = 0
        bits = []
        while True:
            bits.append(es.cur_state('mosi'))
            #print("# w{0} b{1}: '{2}',  t: {3}".format(w_num, b_num, bits[-1], es.cur_time()))
            #b_num += 1
            
            end_time = es.cur_time()
        
            ts, _ = es.advance_to_edge('clk')
            if ts == 0.0: # no more clock edges
                end_decode = True
                break
            
            ts2, _ = es.advance_to_edge('clk')
            if ts2 == 0.0: # no more clock edges
                end_decode = True
                break
            ts += ts2

                
            if ts > prev_ts * 1.05:
                # the word ended
                break
                
            prev_ts = ts
            
        prev_ts = ts
        #w_num += 1
        
        word = 0
        for b in bits[::-1]:
            word = word << 1 | b
        
        nf = SpiFrame((start_time, end_time), word)
        nf.word_size = len(bits)
        nf.cs = start_cs
        
        yield nf
        
        if end_decode:
            break
            
        
            
        # if ts > prev_ts * 1.05:
            # # the word has ended
            # word = 0
            # for b in bits[::-1]:
                # word = word << 1 | b
            
            # start_time = 0
            # end_time = 0
            # nf = spi_frame((start_time, end_time), word)
            
            # yield nf
            # bits = []

        # prev_ts = ts
            
        # print(es.cur_state(), ts, es.sequences[0].cur_time)
    
    # # last word
    # if len(bits) > 0:
        # word = 0
        # for b in bits[::-1]:
            # word = word << 1 | b
        # nf = spi_frame((start_time, end_time), word)            
        # yield (nf, bits)
        
    #ae = [s.at_end() for s in es.sequences]
    #print(ae)
    #print(len(bits))


def spi_synth(data, word_size, clock_freq, cpol=0, cpha=0, lsb_first=True, idle_start=0.0, word_interval=0.0):
        t = 0.0
        clk = cpol
        mosi = 0
        cs = 1
        
        half_bit_period = 1.0 / (2.0 * clock_freq)
        
        
        yield ((t, clk),(t, mosi),(t, cs)) # initial conditions
        t += idle_start
         
        for i, d in enumerate(data):
            bits_remaining = word_size
            bits = [0] * word_size
            for i in xrange(word_size):
                b = d & 0x01
                d = d >> 1
                
                # first bit transmitted will be at the end of the list
                if lsb_first:
                    bits[word_size - 1 - i] = b
                else:
                    bits[i] = b
            
            if cpha == 0: # data goes valid a half cycle before the first clock edge
                t += half_bit_period
                #mosi = d & 0x01
                #d = d >> 1
                mosi = bits[bits_remaining-1]
                bits_remaining -= 1
                cs = 0
                yield ((t, clk),(t, mosi),(t, cs))
                t += half_bit_period
                clk = 1 - clk # initial half clock period
                yield ((t, clk),(t, mosi),(t, cs))
            else:
                t += half_bit_period
                cs = 0
                yield ((t, clk),(t, mosi),(t, cs))
                
            while bits_remaining:
                t += half_bit_period
                clk = 1 - clk
                #mosi = d & 0x01
                #d = d >> 1
                mosi = bits[bits_remaining-1]
                bits_remaining -= 1
                yield ((t, clk),(t, mosi),(t, cs))

                t += half_bit_period
                clk = 1 - clk
                yield ((t, clk),(t, mosi),(t, cs))
                
            t += half_bit_period
            if cpha == 0: # final half clock period
                clk = 1 - clk
            else: # cpha == 1
                if i == len(data) - 1:  # deassert CS at end of data sequence
                    cs = 1
            mosi = 0
            yield ((t, clk),(t, mosi),(t, cs))
            
            if cpha == 0:
                t += half_bit_period
                if i == len(data) - 1: # deassert CS at end of data sequence
                    cs = 1
                yield ((t, clk),(t, mosi),(t, cs))
            
                
            t += word_interval
            
        t += half_bit_period
            
        yield ((t, clk),(t, mosi),(t, cs)) # final state