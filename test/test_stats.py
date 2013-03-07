#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   Statistical operations test suite
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

import unittest
import random

import ripyl.stats as stats
    
# def fequal(a, b, epsilon=0.0001):
    # '''Compare floating point values for relative equality'''
    # return abs(math.log10(a) - math.log10(b)) <= epsilon

    
    
class TestOnlineStats(unittest.TestCase):
    def test_basic(self):
        os = stats.OnlineStats()
        
        data = [1.0] * 100
        for n in data:
            os.accumulate(n)
        
        self.assertAlmostEqual(os.mean(), 1.0, msg='Invalid mean')
        self.assertAlmostEqual(os.variance(), 0.0, msg='Invalid variance')
        self.assertAlmostEqual(os.std(), 0.0, msg='Invalid std. dev.')
        
        os.reset()
        self.assertAlmostEqual(os.mean(), 0.0, msg='Invalid mean')
        self.assertAlmostEqual(os.variance(), 0.0, msg='Invalid variance')
        
        data = range(11)
        for n in data:
            os.accumulate(n)
        
        self.assertAlmostEqual(os.mean(), 5.0, msg='Invalid mean')
        self.assertAlmostEqual(os.std(), 3.16227766, msg='Invalid std. dev.')
        
    def test_rand(self):
        os = stats.OnlineStats()
        
        # uniform random numbers
        for i in xrange(10):
            os.reset()
            for _ in xrange(10000): os.accumulate(random.uniform(0.0, 1.0))
            
            self.assertAlmostEqual(os.mean(), 0.5, places=1, msg='Invalid mean')
            self.assertAlmostEqual(os.std(), 0.28, places=1, msg='Invalid std. dev.')
        

        # gaussian random numbers
        for i in xrange(10):
            os.reset()
            for _ in xrange(1000): os.accumulate(random.gauss(0.5, 0.1))
            
            self.assertAlmostEqual(os.mean(), 0.5, places=1, msg='Invalid mean')
            self.assertAlmostEqual(os.std(), 0.1, places=1, msg='Invalid std. dev.')
            
        # gaussian random numbers 2
        for i in xrange(10):
            os.reset()
            for _ in xrange(1000): os.accumulate(random.gauss(0.5, 0.3))
            
            self.assertAlmostEqual(os.mean(), 0.5, places=1, msg='Invalid mean')
            self.assertAlmostEqual(os.std(), 0.3, places=1, msg='Invalid std. dev.')            