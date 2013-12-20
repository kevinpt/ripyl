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
import time

import ripyl
import ripyl.decode as decode
import ripyl.sigproc as sigp
import test.test_support as tsup



class TestPerformance(unittest.TestCase):

    #@unittest.skip('debug')
    @tsup.timedtest
    def test_edge_finding(self):
        if ripyl.config.settings.cython_active:
            iterations = 100
            cy_status = 'enabled'
        else:
            iterations = 10
            cy_status = 'disabled'

        print('\nDetermining edge processing rate (Cython is {}, {} iterations)...'.format(cy_status, iterations))

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

        self._t_start = time.time()
        for _ in xrange(iterations):
            d_edges = list(decode.find_edges(iter(samples), (0.0, 1.0)))
            #print('### found edges:', len(d_edges), d_edges[:10])

        samples_processed = iterations * (t * sample_rate)
        #print('### samples:', samples_processed, int(t * sample_rate))

        return (iterations, samples_processed, 'samples')

    #@unittest.skip('debug')
    @tsup.timedtest
    def test_multi_edge_finding(self):
        if ripyl.config.settings.cython_active:
            iterations = 100
            cy_status = 'enabled'
        else:
            iterations = 10
            cy_status = 'disabled'

        print('\nDetermining multi-level edge processing rate (Cython is {}, {} iterations)...'.format(cy_status, iterations))

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
        
        samples = list(sigp.synth_wave(iter(edges), sample_rate, sigp.min_rise_time(sample_rate) * 6.0, \
            logic_states=(-1, 1), chunk_size=10000))

        hyst_thresh = decode.gen_hyst_thresholds((0.0, 0.5, 1.0), hysteresis=0.4)


        self._t_start = time.time()
        for _ in xrange(iterations):
            d_edges = list(decode.find_multi_edges(iter(samples), hyst_thresh))

        samples_processed = iterations * (t * sample_rate)
        #print('### samples:', samples_processed, int(t * sample_rate))

        return (iterations, samples_processed, 'samples')


