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

class I2cFrame(StreamSegment):
    def __init__(self, bounds, data=None):
        StreamSegment.__init__(self, bounds, data)
        self.kind = 'I2C frame'
        
    def __str__(self):
        return str(self.data)

class I2C(object):        
    Write = 0
    Read = 1

class I2CTransfer(object):
    def __init__(self, r_wn, address, data):
        self.r_wn = r_wn
        self.address = address
        self.data = data
        
    def bytes(self):
        b = []
        
        if self.address <= 0x77: # 7-bit address
            b.append(self.address | (self.r_wn & 0x01))
        
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


def i2c_synth(transfers, address_bits=7, clock_freq, idle_start=0.0, idle_end=0.0):
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
            bits = [int(c) for c in bin(byte & 0xFF)[2:].rjust(8,'0')]
            bits.extend(ack_bits[j])
            
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
            
            
                
