#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Protocol decode library
   decode.py test suite
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
import math

import ripyl.decode as decode



def fequal(a, b, epsilon=0.0001):
    '''Compare floating point values for relative equality'''
    return abs(math.log10(a) - math.log10(b)) <= epsilon
    
def nearly_equal(a, b, epsilon):
    ''' Adapted from: http://floating-point-gui.de/errors/comparison/ '''
    
    if a == b: # take care of the inifinities
        return True
    
    elif a * b == 0.0: # either a or b is zero
        return abs(a - b) < epsilon ** 2
        
    else: # relative error
        return abs(a - b) / (abs(a) + abs(b)) < epsilon
    


class TestDecodeFuncs(unittest.TestCase):
    def test_find_bot_top_hist_peaks(self):
        pass

    def test_find_symbol_rate(self):
        print('')
        trials = 20
        for i in xrange(trials):
            print('\r  find_symbol_rate() trial {0} / {1}  '.format(i+1, trials), end='')
            
            freq = random.randrange(100, 10000)
            
            # construct a list of edges with random spans
            e = []
            t = 0.0
            for _ in xrange(100):
                n = random.randrange(1, 5)
                t += n / freq
                e.append((t,1)) # we maintain state at constant 1 since find_symbol_rate() doesn't care
            
            spectra = random.randrange(2, 5)
            detected_rate = decode.find_symbol_rate(iter(e), spectra=spectra)
            
            # assertAlmostEqual() can't evaluate the closeness of two integers
            # since it doesn't incorporate relative error
            equal = nearly_equal(detected_rate, freq, epsilon=0.01)
            #print('sr', detected_rate, freq, equal)
            self.assertTrue(equal, msg='symbol rate mismatch {0} != {1}'.format(detected_rate, freq))
            

    
class TestEdgeSequence(unittest.TestCase):
    def test_es(self):
        edges = [(0.0, 0), (0.5,1), (2.0, 0), (4.0, 1)]
        es = decode.EdgeSequence(iter(edges), 1.0)
        
        self.assertEqual(es.cur_state(), 0)
        
        states = [0,0,1,1,1,1,1,1,0,0, 0,0,0,0,0,0,1,1,1,1]
        
        for i, s in zip(xrange(20), states):
            es.advance(0.25)
            #print('@@@ cs', es.cur_state(), states[i])
            self.assertEqual(es.cur_state(), s, 'advance() mismatch')
        
        
        es = decode.EdgeSequence(iter(edges), 1.0)
        states = [1, 0, 1, 1]
        i = 0
        while not es.at_end():
            es.advance_to_edge()
            #print('cs', es.cur_state(), es.cur_time)
            self.assertEqual(es.cur_state(), states[i], 'advance_to_edge() mismatch')
            i += 1
            
        