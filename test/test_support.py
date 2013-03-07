#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   test support functions
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

def read_bin_file(fname):
    import struct
    with open(fname, 'rb') as fo:
        sample_period = struct.unpack('<d', fo.read(8))[0]
        samples = []
        while True:
            s = fo.read(8)
            if len(s) > 0:
                samples.append(struct.unpack('<d', s)[0])
            else:
                break
    
        return (samples, sample_period)