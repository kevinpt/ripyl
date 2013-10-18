#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   Equality functions
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

def relatively_equal(a, b, epsilon):
    '''Evaluate the relative equality of two floats

    The epsilon parameter controls how close the relatve magnitudes need to be
    for equality to be determined.

    Adapted from: http://floating-point-gui.de/errors/comparison/ 

    a (float)
        First number to compare

    b (float)
        Second number to compare

    epsilon (float)
        Relative epsilon for comparison

    Returns True when a and b are nearly equal
    '''
    
    if a == b: # take care of the inifinities
        return True
    
    elif a * b == 0.0: # either a or b is zero
        return abs(a - b) < epsilon ** 2
        
    else: # relative error
        return abs(a - b) / (abs(a) + abs(b)) < epsilon


def min_relative_epsilon(a, b):
    '''Compute the minimum epsilon value for relatively_equal()

    a (float)
        First number to compare

    b (float)
        Second number to compare

    Returns a float representing the minimum epsilon.
    '''
    import math

    if a * b == 0.0:
        return math.sqrt(abs(a - b))
    else:
        return abs(a - b) / (abs(a) + abs(b))


