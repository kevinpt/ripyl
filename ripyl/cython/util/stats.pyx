#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Cython implementation of util/stats.py
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

cimport cython
from libc.math cimport sqrt

cdef class OnlineStats:
    '''Generate statistics from a data set.
    Computes mean, variance and standard deviation in a single pass through a data set.
    '''

    cdef int c
    cdef double m
    cdef double s

    def __init__(self):
        #print 'Cy OnlineStats()'
        self.c = 0
        self.m = 0.0
        self.s = 0.0
        
    def accumulate(self, data):
        '''Add a new data value to the set of accumulated statistics
        
        data (number)
            New data to accumulate statistics on
        '''
        cdef double delta

        #print 'Cy OnlineStats.accumulate()'

        self.c += 1
        delta = data - self.m
        self.m = self.m + delta / float(self.c)
        self.s = self.s + delta * (data - self.m)


    def accumulate_array(self, list data):
        '''Add a new data value to the set of accumulated statistics
        
        data (sequence of numbers)
            New data to accumulate statistics on
        '''

        cdef double delta

        for d in data:
            self.c += 1
            delta = d - self.m
            self.m = self.m + delta / self.c
            self.s = self.s + delta * (d - self.m)


    def variance(self, int ddof=0):
        '''Compute the variance of the data values previously accumulated
        
        ddof (int)
            Delta Degrees of Freedom. Divisor for variance is N - ddof.
            Use 0 for a data set which repsresents an entire population.
            Use 1 for a data set representing a population sample.

        Returns a float for the variance
        '''
        if self.c > 2:
            return self.s / float(self.c - ddof)
        else:
            return 0.0
    
    def std(self, int ddof=0):
        '''Compute the standard deviation of the values previously accumulated
        
        ddof (int)
            [See variance()]

        Returns a float for the standard deviation.
        '''
        return sqrt(self.variance(ddof))
    
    def mean(self):
        '''Returns the mean of the values previously accumulated'''
        return self.m

    def reset(self):
        '''Reset accumulated statistics to initial conditions'''
        self.__init__()

