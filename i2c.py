#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Protocol decode library
   I2C protocol decoder
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

class I2C(object):        
    Write = 0
    Read = 1


class I2cByte(StreamSegment):
    def __init__(self, bounds, data=None, ack_bit=None):
        StreamSegment.__init__(self, bounds, data)
        self.kind = 'I2C byte'
        self.ack_bit = ack_bit
        
    def __str__(self):
        return str(self.data)

        
class I2cAddress(StreamSegment):
    def __init__(self, bounds, data=None, r_wn=None):
        '''
        r_wn
            Read (1) / Write (0) bit
        
        '''
        StreamSegment.__init__(self, bounds, data)
        self.kind = 'I2C address'
        self.r_wn = r_wn
        
    def __str__(self):
        return str(hex(self.data))

def i2c_decode(scl, sda, stream_type=StreamType.Samples):
    '''Decode a I2C data stream
    
    scl
        An iterable representing the I2C serial clock
    
    sda
        An iterable representing the I2C serial data
    
    stream_type
        Indicates the type of stream used for scl and sda.
        
        When StreamType.Samples, the iterators represent a sequence of samples.
        Each sample is a 2-tuple representing the time of the sample and the sample's
        value. When this type is used, the scl stream is analyzed to determine the
        logic levels of the two streams.
        
        When StreamType.Edges, the iterators represent a series of edges.
        scl and sda are iterables of 2-tuples representing each edge transition.
        The 2-tuples *must* be in the absolute time form (time, logic level).

    
    Yields a series of StreamRecord-based objects. These will be one of three event types
    or two data types. The three events are represented by StreamEvent object with these
    obj.kind attributes:
        * 'I2C start'   The start of an I2C transfer
        * 'I2C restart' A start condition during a transfer
        * 'I2C stop'    The end of a transfer
        
    The two data types are represented by the objects I2cAddress and I2cByte. The former
    is a 7-bit or 10-bit address from the start of a transfer or restart. The latter contains
    the data read or written during the transfer. I2cByte has an attribute ack_bit that
    records the value of the ACK for that byte. I2cAddress has a r_wn attribute that indicates
    if the transfer is a read or write. The subrecords attribute contains the I2cByte object
    or objects that composed the address.
    
    Raises StreamError when the stream_type is Samples and the logic levels cannot
    be determined automatically.
    '''

    rec_it = _i2c_decode_ll(scl, sda, stream_type)
    
    S_DATA = 0
    S_ADDR = 1
    S_ADDR_10B = 2
    
    state = S_DATA
    addr_recs = []
    ten_bit_addr = False
    first_addr = None
    
    for r in rec_it:
        if state == S_DATA:
            if r.kind == 'I2C start' or r.kind == 'I2C restart':
                state = S_ADDR
                addr_recs = []
                ten_bit_addr = False
                
            yield r
            
        elif state == S_ADDR:
            if r.data > 0x77: # first 2 bits of 10-bit address
                first_addr = r
                state = S_ADDR_10B
                
            else: # 7-bit address
                r_wn = r.data & 0x01
                na = I2cAddress((r.start_time, r.end_time), r.data >> 1, r_wn)
                na.subrecords.append(r)
                yield na

                state = S_DATA           
        
        else: # S_ADDR_10B
            addr = (((first_addr.data >> 1) & 0x03) << 8) | r.data
            r_wn = first_addr.data & 0x01
            na = I2cAddress((first_addr.start_time, r.end_time), addr, r_wn)
            na.subrecords.append(first_addr)
            na.subrecords.append(r)
            yield na

            state = S_DATA          



def _i2c_decode_ll(scl, sda, stream_type=StreamType.Samples):
    ''' low level I2C decoder'''
    
    if stream_type == StreamType.Samples:
        # tee off an iterator to determine logic thresholds
        s_scl_it, thresh_it = itertools.tee(scl)
        
        logic = find_logic_levels(thresh_it, max_samples=5000)
        if logic is None:
            raise StreamError('Unable to find avg. logic levels of waveform')
        del thresh_it
        
        hyst = 0.4
        scl_it = find_edges(s_scl_it, logic, hysteresis=hyst)
        sda_it = find_edges(sda, logic, hysteresis=hyst)

    else: # the streams are already lists of edges
        scl_it = scl
        sda_it = sda


    edge_sets = {
        'scl': scl_it,
        'sda': sda_it
    }
    
    es = MultiEdgeSequence(edge_sets, 0.0)
    
    S_IDLE = 0
    S_IN_TRANSFER = 1
    state = S_IDLE
    
    start_time = None
    end_time = None
    bits = []
    
    while not es.at_end():
    
        ts, cname = es.advance_to_edge()
        
        if state == S_IDLE:
            if cname == 'sda' and not es.at_end('sda') \
            and es.cur_state('sda') == 0 and es.cur_state('scl') == 1:
                # start condition met
                se = StreamEvent(es.cur_time(), data=None, kind='I2C start')
                yield se
                state = S_IN_TRANSFER
        
        elif state == S_IN_TRANSFER:
            if cname == 'sda' and not es.at_end('sda'):
                if es.cur_state('sda') == 1 and es.cur_state('scl') == 1:
                    # stop condition met
                    se = StreamEvent(es.cur_time(), data=None, kind='I2C stop')
                    yield se
                    state = S_IDLE
                if es.cur_state('sda') == 0 and es.cur_state('scl') == 1:
                    # restart condition met
                    se = StreamEvent(es.cur_time(), data=None, kind='I2C restart')
                    yield se
                    bits = []
                    start_time = None
                    
            if cname == 'scl' and not es.at_end('scl') and es.cur_state('scl') == 1:
                # rising edge of SCL
                
                # accumulate the bit
                if start_time is None:
                    start_time = es.cur_time()
    
                bits.append(es.cur_state('sda'))
                end_time = es.cur_time()
                
                if len(bits) == 9:
                    ack_bit = bits[8]
                    word = 0
                    for b in bits[0:8]:
                        word = word << 1 | (b & 0x01)

                    nb = I2cByte((start_time, end_time), word, ack_bit)
                    yield nb
                    bits = []
                    start_time = None
                    
                    
        
        


class I2CTransfer(object):
    def __init__(self, r_wn, address, data):
        self.r_wn = r_wn
        self.address = address
        self.data = data
        
    def bytes(self):
        b = []
        
        if self.address <= 0x77: # 7-bit address
            b.append((self.address << 1) | (self.r_wn & 0x01))
        
        else: # 10-bit address
            address_upper_bits = (self.address & 0x300) >> 8
            address_lower_bits = self.address & 0xFF
            
            b.append(0x78 | (address_upper_bits << 1) | (self.r_wn & 0x01))
            b.append(address_lower_bits)

        b.extend(self.data)
        return b
        
    def ack_bits(self):
        ack = []
        
        if self.address <= 0x77:
            ack.append(0)
        else:
            ack.extend([0, 0])

        ack.extend([0] * len(self.data))
        if self.r_wn == I2C.Read:
            ack[-1] = 1 # Master nacks last byte of a read
            
        return ack


def i2c_synth(transfers, clock_freq, idle_start=0.0, idle_end=0.0):
    t = 0.0
    sda = 1
    scl = 1
    
    half_bit_period = 1.0 / (2.0 * clock_freq)
    
    yield ((t, scl), (t, sda)) # initial conditions
    t += idle_start
    
    for i, tfer in enumerate(transfers):
        # generate start
        sda = 0
        yield ((t, scl), (t, sda))
        
        t += half_bit_period / 2.0
        scl = 0
        yield ((t, scl), (t, sda))
        
        t += half_bit_period / 2.0
    
        ack_bits = tfer.ack_bits()
        for j, byte in enumerate(tfer.bytes()):
            bits = [int(c) for c in bin(byte & 0xFF)[2:].zfill(8)]
            bits.append(ack_bits[j])
            
            for b in bits:
                sda = b
                yield ((t, scl), (t, sda))
                t += half_bit_period / 2.0
                
                scl = 1
                yield ((t, scl), (t, sda))
                t += half_bit_period
                
                scl = 0
                yield ((t, scl), (t, sda))
                t += half_bit_period / 2.0
                
        # Prep for repeated start unless last transfer
        if i < len(transfers)-1:
            sda = 1
            yield ((t, scl), (t, sda))
            t += half_bit_period / 2.0
            
            scl = 1
            yield ((t, scl), (t, sda))
            t += half_bit_period / 2.0
            
    # generate stop after last transfer
    sda = 0
    yield ((t, scl), (t, sda))
    t += half_bit_period / 2.0
    
    scl = 1
    yield ((t, scl), (t, sda))
    t += half_bit_period / 2.0
    
    sda = 1
    yield ((t, scl), (t, sda))
    t += half_bit_period / 2.0 + idle_end
    
    yield ((t, scl), (t, sda)) # final state
            
            
                
