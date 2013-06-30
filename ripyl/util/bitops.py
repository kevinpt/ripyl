#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Bit-wise operations
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

def split_bits(n, num_bits):
    '''Convert integer to an array of bits (MSB-first)'''
    bits = [0] * num_bits
    for i in xrange(num_bits-1, -1, -1):
        bits[i] = n & 0x01
        n >>= 1
        
    return bits
    
   
def join_bits(bits):
    '''Convert an array of bits (MSB first) to an integer word'''
    word = 0
    for b in bits:
        word = (word << 1) | b
        
    return word
