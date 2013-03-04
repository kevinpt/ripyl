#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Protocol decode library
   Statistical operations test suite
'''

# Copyright © 2013 Kevin Thibedeau

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