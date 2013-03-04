#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Protocol decode library
   Statistical operations
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

import math

        
class OnlineStats(object):
    '''Generate statistics from a data set.
    Computes mean, variance and standard deviation in a single pass through a data set.
    '''
    def __init__(self):
        self.c = 0
        self.m = 0.0
        self.s = 0.0
        
    def accumulate(self, d):
        '''Add a new data value to the set of accumulated statistics'''
        self.c += 1
        delta = d - self.m
        self.m = self.m + delta / self.c
        self.s = self.s + delta * (d - self.m)
    
    def variance(self, ddof=0):
        '''Return the variance of the data values previously accumulated
        
        ddof
            Delta Degrees of Freedom. Divisor for variance is N - ddof.
            Use 0 for a data set which repsresents an entire population.
            Use 1 for a data set representing a population sample.
        '''
        if self.c > 2:
            return self.s / (self.c - ddof)
        else:
            return 0.0
    
    def std(self, ddof=0):
        '''Return standard deviation of the values previously accumulated
        
        ddof
            [See variance()]
        '''
        return math.sqrt(self.variance(ddof))
    
    def mean(self):
        '''Return the mean of the values previously accumulated'''
        return self.m

    def reset(self):
        '''Reset accumulated statistics to initial conditions'''
        self.__init__()
        
