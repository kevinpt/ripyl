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
import ripyl.sigproc as sigp
import test.test_support as tsup


class TestDecodeFuncs(tsup.RandomSeededTestCase):

    #@unittest.skip('debug')
    def test_find_symbol_rate(self):
        self.test_name = 'find_symbol_rate() test'
        self.trial_count = 40
        for i in xrange(self.trial_count):
            self.update_progress(i+1)

            freq = random.randrange(100, 10000)
            
            # construct a list of edges with random spans
            e = []
            t = 0.0
            for _ in xrange(200):
                n = random.randrange(1, 5)
                t += n / freq
                e.append((t,1)) # we maintain state at constant 1 since find_symbol_rate() doesn't care
            
            spectra = random.randrange(2, 5)

            for s in xrange(spectra, 1, -1):
                detected_rate = decode.find_symbol_rate(iter(e), spectra=s)
                if detected_rate > 0:
                    break
            
            # assertAlmostEqual() can't evaluate the closeness of two integers
            # since it doesn't incorporate relative error
            equal = tsup.relativelyEqual(detected_rate, freq, epsilon=0.01)
            # print('sr', detected_rate, freq, equal)

            if not equal:
                print('  num spectra:', spectra)
                print(e)
                
            self.assertTrue(equal, msg='symbol rate mismatch {0} != {1}'.format(detected_rate, freq))

    #@unittest.skip('debug')
    def test_find_logic_levels(self):
        # test with clean samples
        # with noise
        # with bandwidth limited (slow and fast)
        # with noise and bandwidth limit

        # with first edge before 200th sample, just before 200th, just after 200th, after 200th


        sample_rate = 1000.0
        sample_period = 1.0 / sample_rate
        rise_time = sigp.min_rise_time(sample_rate) * 50.0

        edge_vectors = {
            'flat_line': (((0.0,0), (3.0,0)), False),
            'rising_edge_100': (((0.0,0), (0.10,1), (3.0,1)), False),
            'rising_edge_190': (((0.0,0), (0.19,1), (3.0,1)), True),
            'rising_edge_200': (((0.0,0), (0.2,1),  (3.0,1)), True),
            'rising_edge_400': (((0.0,0), (0.40,1), (3.0,1)), True),
            'pulse_100': (((0.0,0), (0.10,1), (0.5,0), (3.0,0)), True),
            'multi_pulse': (((0.0,0), (0.7, 1), (0.8, 0), (0.9, 1), (1.0, 0), \
                (1.1,1), (1.2,0), (1.3,1), (1.4,0), \
                (1.5,1), (1.6,0), (3.0,1)), True),
        }

        no_noise_vectors = ('rising_edge_190', 'rising_edge_200')

        sample_vectors = {}
        for name, vector in edge_vectors.iteritems():
            samples = list(sigp.edges_to_sample_stream(iter(vector[0]), sample_period))
            sample_vectors[name] = (samples, vector[1])

        base_names = sample_vectors.keys()
        for name in base_names:
            if name in no_noise_vectors:
                continue
            noisy = list(sigp.noisify(iter(sample_vectors[name][0]), snr_db=20.0))
            sample_vectors['noisy_' + name] = (noisy, sample_vectors[name][1])

        for name in base_names:
            bwlim = list(sigp.filter_waveform(iter(sample_vectors[name][0]), sample_rate, rise_time))
            sample_vectors['bwlim_' + name] = (bwlim, sample_vectors[name][1])

        for name in base_names:
            if name in no_noise_vectors:
                continue
            bwlim_noisy = list(sigp.noisify(sigp.filter_waveform(iter(sample_vectors[name][0]), \
                sample_rate, rise_time), snr_db=20.0))
            sample_vectors['bwlim_noisy_' + name] = (bwlim_noisy, sample_vectors[name][1])


        #sample_vectors.pop('rising_edge_400', None)

        for name, vector in sample_vectors.iteritems():
            samples = vector[0]
            expect_success = vector[1]

            logic_levels = decode.find_logic_levels(samples)
            if not expect_success:
                continue # We expected find_logic_levels() to fail

            if logic_levels is None:
                #print('### Fail:', name)
                self.fail('No logic levels found')


            #print('####', name, logic_levels)
            self.assertRelativelyEqual(logic_levels[0], 0.0, epsilon=0.16, msg='Bad logic 0: {}'.format(logic_levels[0]))
            self.assertRelativelyEqual(logic_levels[1], 1.0, epsilon=0.1, msg='Bad logic 1: {}'.format(logic_levels[1]))


    def test_find_multi_edges(self):
        self.test_name = 'find_multi_edges() test'
        self.trial_count = 100
        for i in xrange(self.trial_count):
            self.update_progress(i+1)

            bit_period = 1.0
            sample_rate = bit_period * 1000
            rt = sigp.min_rise_time(sample_rate) * random.uniform(20.0, 200.0)

            num_states = random.randint(2, 7)
            offset = (2 * (num_states - 1)) // 4
            logic_states = (0 - offset, num_states - 1 - offset)
            #print('\nlogic states:', logic_states, num_states)

            # Generate random edges
            prev_state = 0
            state = 0
            edges = []
            t = 0.0
            for _ in xrange(10):
                while state == prev_state: # Guarantee that each edge is different from the previous
                    state = random.randint(logic_states[0], logic_states[-1])

                prev_state = state
                edges.append((t, state))
                t += bit_period

            # Duplicate the last edge so that it will be decoded
            edges = edges + [(edges[-1][0] + bit_period, edges[-1][1])]

            #print('## edges:', edges)

            samples = sigp.synth_wave(iter(edges), sample_rate, rt, logic_states=logic_states)

            # Generate logic levels in range [0.0, 1.0]
            logic_levels = [float(level) / (num_states-1) for level in xrange(num_states)]
            #print('## logic_levels:', logic_levels)
            found_edges = list(decode.find_multi_edges(samples, decode.gen_hyst_thresholds(logic_levels)))
            #print('## found:', found_edges)

            # Remove brief transitional states that last less than half the bit period
            rts_edges = list(decode.remove_transitional_states(iter(found_edges), bit_period * 0.5))
            #print('\n## RTS edges:', rts_edges)

            edges = edges[:-1] # Trim off last (duplicate) edge
            self.assertEqual(len(edges), len(rts_edges), msg='Mismatch in found edge count {} != {}'.format(len(edges), len(rts_edges)))

            for i, (e, f) in enumerate(zip(edges, rts_edges)):
                self.assertRelativelyEqual(e[0], f[0], epsilon=0.5, msg='Edge times not close enough {} != {}'.format(e[0], f[0]))
                self.assertEqual(e[1], f[1], msg='Edges not the same index={}, edge={}, found={}'.format(i, e[1], f[1]))

    
class TestEdgeSequence(unittest.TestCase):
    @unittest.skip('debug')
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
            
        
