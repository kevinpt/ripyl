#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Protocol decode library
   UART protocol decoder
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
from streaming import *

class UartFrame(StreamSegment):
    '''Frame object for UART data'''
    def __init__(self, bounds, data=None):
        StreamSegment.__init__(self, bounds, data)
        self.kind = 'UART frame'
        
    def __str__(self):
        return chr(self.data)

def uart_decode(stream, bits=8, parity=None, stop_bits=1.0, lsb_first=True, inverted=False, \
    baud_rate=None, use_std_baud=True, stream_type=StreamType.Samples, baud_deque=None):
    
    '''Decode a UART data stream

    This is a generator function that can be used in a pipeline of waveform
    procesing operations.
    
    stream
        A stream of 2-tuples of (time, value) pairs. The type of stream is identified
        by the stream_type parameter. Either a series of real valued samples that will
        be analyzed to find edge transitions or a set of pre-processed edge transitions
        representing the 0 and 1 logic states of the UART waveform. When this is a sample
        stream, an initial block of data is consumed to determine the most likely logic
        levels in the signal.
    
    bits
        The number of bits in each word. Typically 5, 7, 8, or 9.
    
    parity
        The type of parity to use. One of None, 'even', or 'odd'
    
    stop_bits
        The number of stop bits. Typically 1, 1.5, or 2
    
    lsb_first
        Boolean indicating whether the Least Significant Bit is transmitted first.
    
    inverted
        Boolean indicating if the signal levels have been inverted from their logical
        meaning. Use this when the input stream derives from an inverting driver such
        as those used for RS-232.
    
    baud_rate
        The baud rate of the stream. If None, the first 50 edges will be analyzed to
        automatically determine the most likely baud rate for the stream
    
    use_std_baud
        Boolean that forces coercion of automatically detected baud rate to the set of
        standard rates
    
    stream_type
        A StreamType value indicating that the stream parameter represents either Samples
        or Edges
        
    baud_deque
        An optional collections.deque object that is used to monitor the results of
        automatic baud detection. A dict containing the internal variables baud_rate
        and raw_symbol_rate is placed on the deque when uart_decode() is called.

        
    Yields a series of UartFrame objects. Each frame contains subrecords marking the location
      of sub-elements within the frame (start, data, parity, stop). Parity errors are recorded
      as an error status in the parity subrecord.
      
    Raises StreamError if stream_type = Samples and the logic levels cannot
      be determined. Also if auto-baud is active and the baud rate cannot
      be determined.
      
    Raises ValueError is the parity argument is invalid.
    '''

    if stream_type == StreamType.Samples:
        # tee off an iterator to determine logic thresholds
        samp_it, thresh_it = itertools.tee(stream)
        
        logic = find_logic_levels(thresh_it, max_samples=5000, buf_size=2000)
        if logic is None:
            raise StreamError('Unable to find avg. logic levels of waveform')
        del thresh_it
        
        edges = find_edges(samp_it, logic, hysteresis=0.4)
    else: # the stream is already a list of edges
        edges = stream
        
    
    raw_symbol_rate = 0
    
    if baud_rate is None:
        # Find the baud rate
        
        # tee off an independent iterator to determine baud rate
        edges_it, sre_it = itertools.tee(edges)
        
        # Experiments on random data indicate that find_symbol_rate() will almost
        # always converge to a close estimate of baud rate within the first 35 edges.
        # It seems to be a guarantee after 50 edges (pathological cases not withstanding).
        min_edges = 50
        symbol_rate_edges = itertools.islice(sre_it, min_edges)
        
        # We need to ensure that we can pull out enough edges from the iterator slice
        # Just consume them all for a count        
        sre_list = list(symbol_rate_edges)
        if len(sre_list) < min_edges:
            raise StreamError('Unable to compute automatic baud rate.')
        
        raw_symbol_rate = find_symbol_rate(iter(sre_list), spectra=2)
        
        # delete the tee'd iterators so that the internal buffer will not grow
        # as the edges_it is advanced later on
        del symbol_rate_edges
        del sre_it
        
        std_bauds = (110, 300, 600, 1200, 2400, 4800, 9600, 14400, 19200, 28800, 38400, \
                     56000, 57600, 115200, 128000, 153600, 230400, 256000, 460800, 921600)

        if use_std_baud:
            # find the standard baud closest to the raw rate
            baud_rate = min(std_bauds, key=lambda x: abs(x - raw_symbol_rate))
        else:
            baud_rate = raw_symbol_rate
            
        #print('@@@@@@@@@@ baud rate:', baud_rate, raw_symbol_rate)
        
    else:
        edges_it = edges
        
        
    if not baud_deque is None:
        bd_dict = {'baud_rate': baud_rate, 'raw_symbol_rate': raw_symbol_rate}
        if stream_type == StreamType.Samples:
            bd_dict['logic'] = logic
            
        edge_list = list(edges_it)
        bd_dict['edges'] = edge_list
        edges_it = iter(edge_list)
        baud_deque.append(bd_dict)
    
    bit_period = 1.0 / float(baud_rate)
    es = EdgeSequence(edges_it, bit_period)
    
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
        
        # We could have an anamolous edge at the end of the edge list
        # Check if edge sequence is complete after our advance
        if es.at_end():
            break
        
        start_time = es.cur_time
        data_time = es.cur_time + bit_period
        es.advance(bit_period * 1.5) # move to middle of first data bit
        
        byte = 0
        cur_bit = 0
        
        p = 0
        if not parity is None:
            if parity == 'even':
                p = 0
            elif parity == 'odd':
                p = 1
            else:
                raise ValueError('Invalid parity argument')
                
        while cur_bit < bits:
            bit_val = es.cur_state()
            if not inverted:
                bit_val = 1 - bit_val
            
            p ^= bit_val
            if lsb_first:
                byte = byte >> 1 | (bit_val << (bits-1))
            else:
                byte = byte << 1 | bit_val
                
            cur_bit += 1
            es.advance()
            #print(es.cur_time)
            
        data_end_time = es.cur_time - bit_period * 0.5
        parity_error = False
        if not parity is None:
            parity_time = data_end_time
            parity_val = es.cur_state()
            if not inverted:
                parity_val = 1 - parity_val
            #print('PB:', p, parity_val)
            # check the parity
            if parity_val != p:
                parity_error = True
            es.advance()
        
        stop_time = es.cur_time - bit_period * 0.5
        # FIX: verify stop bit
        
        end_time = es.cur_time + bit_period * (stop_bits - 0.5)
        
        # construct frame objects
        nf = UartFrame((start_time, end_time), byte)
        
        nf.subrecords.append(StreamSegment((start_time, data_time), kind='start bit'))
        nf.subrecords.append(StreamSegment((data_time, data_end_time), byte, kind='data bits'))
        if not parity is None:
            status = StreamStatus.Error if parity_error else StreamStatus.Ok
            nf.subrecords.append(StreamSegment((parity_time, stop_time), kind='parity', status=status))
            
        nf.subrecords.append(StreamSegment((stop_time, end_time), kind='stop bit'))
            
        #print(byte, bin(byte), chr(byte))
        yield nf
        
    

def uart_synth(data, bits = 8, baud=115200, parity=None, stop_bits=1.0, idle_start=0.0, word_interval=100.0e-7):
    '''Generate synthesized UART waveform
    
    This function simulates a single, unidirectional channel of a UART serial
    connection. Its output is analagous to txd.
    
    This is a generator function that can be used in a pipeline of waveform
    procesing operations.
    
    data
        A sequence of words that will be transmitted serially
    
    bits
        The number of bits in each word. Typically 5, 7, 8, or 9.
    
    baud
        The baud rate
        
    parity
        The type of parity to use. One of None, 'even', or 'odd'
    
    stop_bits
        The number of stop bits. Typically 1, 1.5, or 2
    
    idle_start
        The amount of idle time before the transmission of data begins
    
    word_interval
        The amount of time between data words

    Yields a series of 2-tuples (time, value) representing the time and
      logic value (0 or 1) for each edge transition on txd. The first tuple
      yielded is the initial state of the waveform. All remaining
      tuples are edges where the txd state changes.
        
    '''
    bit_period = 1.0 / baud
    
    t = 0.0
    txd = 1
    
    yield (t, txd) # set initial conditions
    t += idle_start
    
    for d in data:
        txd = 0
        yield (t, txd) # falling edge of start bit
        t += bit_period
        bits_remaining = bits

        p = 0
        if not parity is None:
            if parity == 'even':
                p = 0
            elif parity == 'odd':
                p = 1
            else:
                raise ValueError('Invalid parity argument')        
        
        while bits_remaining:
            next_bit = d & 0x01
            p ^= next_bit
            d = d >> 1
            bits_remaining -= 1
            
            if txd != next_bit:
                txd = next_bit
                yield (t, txd)
            t += bit_period
            
        if not parity is None:
            txd = p
            yield (t, txd)
            t += bit_period
            
            
        if txd == 0: 
            txd = 1
            yield (t, txd)
        t += stop_bits * bit_period # add stop bit
        t += word_interval
        
    yield (t, txd)
