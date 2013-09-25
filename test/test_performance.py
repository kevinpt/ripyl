#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   Performance testing
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
#import math
#import sys

import ripyl
import ripyl.decode as decode
import ripyl.sigproc as sigp
#import test.test_support as tsup
#import ripyl.streaming as stream

import time
import gc
from ripyl.util.eng import eng_si

def timedtest(f):
    def wrapper(self, *args, **kwargs):
        gc.disable()
        try:
            t_start = time.time()
            result = f(self, *args, **kwargs)
            t_end = time.time()
            try:
                _t_start = self._t_start
                t_start = _t_start if isinstance(_t_start, float) else t_start
                self._t_start = None
            except:
                pass

        finally:
            gc.enable()

        delta = t_end - t_start

        iterations = None
        units_processed = 1
        unit_name = 'units'
        if result:
            try:
                if len(result) >= 2:
                    iterations = result[0]
                    units_processed = result[1]

                    if len(result) >= 3:
                        unit_name = result[2]
            except TypeError:
                iterations = result
            

        if iterations:
            per_iter = delta / iterations
        else:
            per_iter = delta

        processing_rate = units_processed / delta

        print('*   Test duration: total {}, per iteration {}, rate {}'.format( \
            eng_si(delta, 's'), eng_si(per_iter, 's'), eng_si(processing_rate, unit_name + '/s') ))

    return wrapper



class TestPerformance(unittest.TestCase):

    #@unittest.skip('debug')
    @timedtest
    def test_edge_finding(self):
        cy_status = 'enabled' if ripyl.config.settings.cython_active else 'disabled'
        print('\nDetermining edge processing rate (Cython is {})...'.format(cy_status))

        edge_count = 1000
        states = [0, 1] * (edge_count // 2)

        period = 1.0
        intervals = [random.randint(1,15) * period for _ in xrange(len(states))]

        t = 0.0
        edges = [(t, states[0])]
        for i in xrange(len(states)):
            t += intervals[i]
            edges.append((t, states[i]))


        sample_rate = 20 / period
        samples = list(sigp.synth_wave(iter(edges), sample_rate, sigp.min_rise_time(sample_rate) * 6.0, chunk_size=10000))

        iterations = 100

        self._t_start = time.time()
        for _ in xrange(iterations):
            d_edges = list(decode.find_edges(iter(samples), (0.0, 1.0)))
            #print('### found edges:', len(d_edges), d_edges[:10])

        samples_processed = iterations * (t * sample_rate)
        #print('### samples:', samples_processed, int(t * sample_rate))

        return (iterations, samples_processed, 'samples')

    #@unittest.skip('debug')
    @timedtest
    def test_multi_edge_finding(self):
        cy_status = 'enabled' if ripyl.config.settings.cython_active else 'disabled'
        print('\nDetermining multi-level edge processing rate (Cython is {})...'.format(cy_status))

        edge_count = 1000
        states = [-1, 0, 1] * (edge_count // 2)

        period = 1.0
        intervals = [random.randint(1,15) * period for _ in xrange(len(states))]

        t = 0.0
        edges = [(t, states[0])]
        for i in xrange(len(states)):
            t += intervals[i]
            edges.append((t, states[i]))


        sample_rate = 20 / period
        
        samples = list(sigp.synth_wave(iter(edges), sample_rate, sigp.min_rise_time(sample_rate) * 6.0, (-1, 1), chunk_size=10000))

        hyst_thresh = decode.gen_hyst_thresholds((0.0, 0.5, 1.0), 0.4)

        iterations = 100

        self._t_start = time.time()
        for _ in xrange(iterations):
            d_edges = list(decode.find_multi_edges(iter(samples), hyst_thresh))

        samples_processed = iterations * (t * sample_rate)
        #print('### samples:', samples_processed, int(t * sample_rate))

        return (iterations, samples_processed, 'samples')


