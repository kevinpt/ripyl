#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   decode.py test suite
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
import math
import sys

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
    def setUp(self):
        import time
        import os
        
        # Use seed from enviroment if it is set
        try:
            seed = long(os.environ['TEST_SEED'])
        except KeyError:
            random.seed()
            seed = long(random.random() * 1e9)

        print('\n * Random seed: {} *'.format(seed))
        random.seed(seed)

    def test_find_bot_top_hist_peaks(self):
        pass

    def test_find_symbol_rate(self):
        print('')
        trials = 40
        for i in xrange(trials):
            print('\r  find_symbol_rate() trial {0} / {1}  '.format(i+1, trials), end='')
            sys.stdout.flush()
            
            freq = random.randrange(100, 10000)
            
            # construct a list of edges with random spans
            e = []
            t = 0.0
            for _ in xrange(200):
                n = random.randrange(1, 5)
                t += n / freq
                e.append((t,1)) # we maintain state at constant 1 since find_symbol_rate() doesn't care
            
            spectra = random.randrange(2, 5)
            detected_rate = decode.find_symbol_rate(iter(e), spectra=spectra)
            
            # assertAlmostEqual() can't evaluate the closeness of two integers
            # since it doesn't incorporate relative error
            equal = nearly_equal(detected_rate, freq, epsilon=0.01)
            # print('sr', detected_rate, freq, equal)
                
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
            
        
