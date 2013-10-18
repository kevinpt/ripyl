#!/usr/bin/python
# -*- coding: utf-8 -*-
# xcython: profile=True
# cython: boundscheck=False
# cython: wraparound=False

'''Cython implementation of sigproc.py functions
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
cimport numpy as np
import numpy as np

from ripyl.streaming import SampleChunk, StreamError


def capacify(samples, capacitance, resistance=1.0, iterations=80):
    '''Simulate an RC filter on a waveform::

        : samples >--R--+--> out
        :               |
        :               C
        :              _|_

    Warning: This function becomes unstable for small time constants (C * R).
    It is implemented with a simple application of the RC difference equations.
    The time step (dt) is taken from the sample period of each sample chunk divided
    by the number of iterations. The results will be inaccurate for large values of
    dt but still largely representative of the expected behavior.

    This is a generator function.

    samples (iterable of SampleChunk objects)
        An iterable sample stream to modify.

    capacitance (float)
        The capacitance value. If resistance is kept at the default value of 1.0 Ohms
        this parameter is equivalent to the time constant tau (c = tau / r).

    resistance (float)
        The resistance value

    iterations (int)
        The number of iterations to calculate each sample. You can experience numeric
        instability if this value is too low.
    
    Yields a sample stream.
    '''

    cdef double q, dt, sample_v, vc
    cdef unsigned int j
    cdef bint vc_init
    cdef double [:] chunk, v_filt

    cdef double c_capacitance = capacitance
    cdef double c_resistance = resistance
    cdef unsigned int c_iterations = iterations

    vc_init = False
    for sc in samples:
        chunk = sc.samples
        if not vc_init: # Set initial conditions for capacitor voltage and charge
            vc = chunk[0] #sc.samples[0]
            q = vc * capacitance

        dt = sc.sample_period / iterations
        #print('# vc', vc, capacitance, q, vc * capacitance, dt)
        filt = np.zeros((len(chunk),), dtype = np.float)
        v_filt = filt
        for j in xrange(len(chunk)):
            sample_v = chunk[j]
            with nogil:
                vc = _capacify_inner_loop(c_iterations, c_capacitance, c_resistance, dt, sample_v, vc, &q)
            v_filt[j] = vc
        yield SampleChunk(filt, sc.start_time, sc.sample_period)


cdef double _capacify_inner_loop(unsigned int iterations, double capacitance, double resistance, \
    double dt, double sample_v, double vc, double *q_p) nogil:

    cdef double i, dq, q

    q = q_p[0]

    for _ in xrange(iterations):
        i = (sample_v - vc) / resistance # Capacitor current

        dq = i * dt # Change in charge
        q = q + dq
        vc = q / capacitance # New capacitor voltage

    q_p[0] = q

    return vc
    


def edges_to_sample_stream(edges, sample_period, logic_states=(0,1), end_extension=None, chunk_size=10000):
    '''Convert an edge stream to a sample stream

    The output samples are scaled to the range of 0.0 to 1.0 regardless of the number of logic states.
    
    edges (iterable of (float, int) tuples)
        An edge stream to sample
        
    sample_period (float)
        The sample period for converting the edge stream

    logic_states (sequence of int)
        The coded state values for the lowest and highest state in the edge stream.
        For 2-level states these will be (0,1). For 3-level: (-1, 1). For 5-level: (-2, 2).
        
    end_extension (float)
        Optional amount of time to add to the end after the last edge transition

    chunk_size (int)
        Number of samples in each SampleChunk
    
    Yields a stream of SampleChunk objects.
    '''
    cdef double t = 0.0
    cdef double c_sample_period = sample_period
    cdef int chunk_count = 0
    cdef int c_chunk_size = chunk_size
    cdef np.ndarray chunk = np.empty(c_chunk_size, dtype=float)
    cdef double[:] chunk_d = chunk
    cdef double start_time
    cdef double offset
    cdef double scale
    cdef double end_time
    cdef double next_edge_time
    cdef double cur_level
    
    try:
        cur_states = next(edges)
        next_states = next(edges)
    except StopIteration:
        raise StreamError('Not enough edges to generate samples')
    
    t = cur_states[0]
    #chunk = np.empty(chunk_size, dtype=float)
    #chunk_count = 0
    start_time = cur_states[0]

    offset = -min(logic_states)
    scale = 1.0 / (max(logic_states) - min(logic_states))

    while True: # Main loop generating samples
        next_edge_time = next_states[0]
        cur_level = (cur_states[1] + offset) * scale
        while t < next_edge_time:
            chunk_d[chunk_count] = cur_level
            chunk_count += 1
            
            t += c_sample_period
            if chunk_count == c_chunk_size:
                yield SampleChunk(chunk, start_time, c_sample_period)

                chunk = np.empty(c_chunk_size, dtype=float)
                chunk_d = chunk
                chunk_count = 0
                start_time = t
        
        cur_states = next_states
        try:
            next_states = next(edges)
        except StopIteration:
            break
            
    if end_extension is not None:
        end_time = t + end_extension
        cur_level = (cur_states[1] + offset) * scale
        while t < end_time:
            chunk_d[chunk_count] = cur_level
            chunk_count += 1

            t += c_sample_period
            if chunk_count == c_chunk_size:
                yield SampleChunk(chunk, start_time, c_sample_period)

                chunk = np.empty(c_chunk_size, dtype=float)
                chunk_d = chunk
                chunk_count = 0
                start_time = t

    if chunk_count > 0:
        yield SampleChunk(chunk[:chunk_count], start_time, c_sample_period)

