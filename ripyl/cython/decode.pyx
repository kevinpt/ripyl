#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Cython implementation of decode.py functions
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

# states
cdef int ES_START = 0
cdef int ZONE_1_L1 = 1 # logic 1
cdef int ZONE_2_T  = 2 # transition
cdef int ZONE_3_L0 = 3 # logic 0

def find_edges(sample_chunks, logic, hysteresis=0.4):
    cdef double span = logic[1] - logic[0]
    cdef double thresh = (logic[1] + logic[0]) / 2.0
    cdef double hyst_top = span * (0.5 + hysteresis / 2.0) + logic[0]
    cdef double hyst_bot = span * (0.5 - hysteresis / 2.0) + logic[0]

    cdef int state = ES_START

    cdef double t, sample_period
    cdef double [:] chunk

    #print 'cy find_edges()'

    for sc in sample_chunks:
        t = sc.start_time
        sample_period = sc.sample_period
        chunk = sc.samples

        if state == ES_START:
            initial_state = (t, 1 if chunk[0] > thresh else 0)
            yield initial_state


        edges, state = _cy_find_edges(chunk, t, sample_period, hyst_top, hyst_bot, state)
        for e in edges:
            yield e

cdef inline bint _is_stable_zone(int zone):
    return zone == ZONE_1_L1 or zone == ZONE_3_L0
    
cdef inline int _zone_to_logic_state(int zone):
    cdef int ls = 999
    if zone == ZONE_1_L1: ls = 1
    elif zone == ZONE_3_L0: ls = 0
    
    return ls

@cython.boundscheck(False)
cdef _cy_find_edges(double[:] chunk, double t, double sample_period, double hyst_top, double hyst_bot, int state):
    cdef int zone
    cdef double sample
    cdef unsigned int i, I

    edges = []

    #for sample in chunk:
    I = chunk.shape[0]
    for i in xrange(I):
        sample = chunk[i]
    
        if sample > hyst_top:
            zone = ZONE_1_L1
        elif sample > hyst_bot:
            zone = ZONE_2_T
        else:
            zone = ZONE_3_L0
        
        if state == ES_START:
            # Stay in start until we reach one of the stable states
            if _is_stable_zone(zone):
                state = zone

        # last zone was a stable state
        elif state == ZONE_1_L1 or state == ZONE_3_L0:
            if _is_stable_zone(zone):
                if zone != state:
                    state = zone
                    edges.append((t, _zone_to_logic_state(zone)))
            else:
                prev_stable = state
                state = zone
        
        # last zone was a transitional state (in hysteresis band)
        elif state == ZONE_2_T:
            if _is_stable_zone(zone):
                if zone != prev_stable: # This wasn't just noise
                    edges.append((t, _zone_to_logic_state(zone)))

            state = zone


        t += sample_period

    return edges, state

