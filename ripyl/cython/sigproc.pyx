#!/usr/bin/python
# -*- coding: utf-8 -*-

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

from ripyl.streaming import SampleChunk

@cython.boundscheck(False)
def capacify(samples, capacitance, resistance=50.0, iterations=80):
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
        The capacitance value

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
    

