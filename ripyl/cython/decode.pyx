#!/usr/bin/python
# -*- coding: utf-8 -*-

# cython: boundscheck=False
# cython: wraparound=False

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

#from libc.stdlib cimport malloc, free

ctypedef struct cEdge:
    double time
    int state

cdef class Edge:
    cdef cEdge c

    property time:
        def __get__(self):
            return self.c.time

        def __set__(self, value):
            self.c.time = value

    property state:
        def __get__(self):
            return self.c.state

        def __set__(self, value):
            self.c.state = value


    def __cinit__(self, double time, int state):
        self.time = time
        self.state = state

    def __getitem__(self, index):
        #cdef int ix

        #if isinstance(index, slice):
        #    ix = index.indices(1).start
        #else:
        #    ix = index


        if index == 0:
            return self.time
        else:
            return self.state

    def __iter__(self):
        return iter((self.time, self.state))


# states

# NOTE: declaring these constants as ints rather than enums ends up creating
# faster execution in the generated code
cdef int ES_START = 1000
cdef int ZONE_1_L1 = 2 # logic 1
cdef int ZONE_2_T  = 1 # transition
cdef int ZONE_3_L0 = 0 # logic 0


def find_edges(sample_chunks, logic, hysteresis=0.4):
    cdef double span = logic[1] - logic[0]
    cdef double thresh = (logic[1] + logic[0]) / 2.0
    cdef double hyst_top = span * (0.5 + hysteresis / 2.0) + logic[0]
    cdef double hyst_bot = span * (0.5 - hysteresis / 2.0) + logic[0]

    cdef int state = ES_START
    cdef int prev_stable

    cdef double t, sample_period
    cdef double [:] chunk

    #print 'cy find_edges()'

    for sc in sample_chunks:
        t = sc.start_time
        sample_period = sc.sample_period
        chunk = sc.samples

        if state == ES_START:
            initial_state = (t, 1 if chunk[0] > thresh else 0)
            prev_stable = ZONE_1_L1 if chunk[0] > thresh else ZONE_3_L0
            yield initial_state

        edges = _cy_find_edges(chunk, t, sample_period, hyst_top, hyst_bot, &state, &prev_stable)
        for e in edges:
            yield e
            #yield Edge(e.time, e.state)


@cython.boundscheck(False)
cdef _cy_find_edges(double[:] chunk, double t, double sample_period, double hyst_top, double hyst_bot, \
    int *p_state, int *p_prev_stable):

    cdef int zone
    cdef bint zone_is_stable
    cdef double sample
    cdef size_t i
    cdef int state, prev_stable

    edges = []
    
    state = p_state[0]
    prev_stable = p_prev_stable[0]

    #for sample in chunk:
    for i in xrange(chunk.shape[0]):
        sample = chunk[i]
    
        if sample > hyst_top:
            zone = ZONE_1_L1
        elif sample > hyst_bot:
            zone = ZONE_2_T
        else:
            zone = ZONE_3_L0
        zone_is_stable = zone == ZONE_1_L1 or zone == ZONE_3_L0
        
        if state == ES_START:
            # Stay in start until we reach one of the stable states
            if zone_is_stable:
                state = zone

        # last zone was a stable state
        elif state == ZONE_1_L1 or state == ZONE_3_L0:
            if zone_is_stable:
                if zone != state:
                    state = zone
                    edges.append((t, zone // 2))
                    #edges.append(Edge(t, zone // 2))
                    #e.time = t
                    #e.state = zone // 2
                    #edge_list[el_ix] = e
                    #el_ix += 1
                    
            else:
                prev_stable = state
                state = zone
        
        # last zone was a transitional state (in hysteresis band)
        elif state == ZONE_2_T:
            if zone_is_stable:
                if zone != prev_stable: # This wasn't just noise
                    edges.append((t, zone // 2))
                    #edges.append(Edge(t, zone // 2))
                    #e.time = t
                    #e.state = zone // 2
                    #edge_list[el_ix] = e
                    #el_ix += 1


            state = zone

        t += sample_period

    p_state[0] = state
    p_prev_stable[0] = prev_stable

    return edges



def find_multi_edges(samples, hyst_thresholds):
    cdef int zone_offset
    cdef int state = ES_START
    cdef int prev_stable
    cdef size_t i

    cdef double t, sample_period
    cdef double [:] chunk
    
    cdef list center_thresholds
    #cdef double *h_t
    # NOTE: For some reason we segfault if we assign to a malloc'ed h_t array
    # We'll just statically allocate it until a solution can be found
    cdef double h_t[16] 


    assert len(hyst_thresholds) % 2 == 0, 'There must be an even number of hyst_thresholds'
    assert len(hyst_thresholds) <= sizeof(h_t) // sizeof(double), 'hyst_thresholds is too large'

    #print('## cy multi edges')

    # To establish the initial state we need to compare the first sample against thresholds
    # without involving any hysteresis. We compute new thresholds at the center of each
    # hysteresis pair.
    center_thresholds = []
    for i in xrange(0, len(hyst_thresholds), 2):
        center_thresholds.append((hyst_thresholds[i] + hyst_thresholds[i+1]) / 2.0)


    # Compute offset between zone codings and the final logic state coding
    zone_offset = len(hyst_thresholds) // 4
    
    # NOTE: The remaining states have the same encoding as the zone numbers.
    # These are integers starting from 0. Even zones represent stable states
    # corresponding to the logic levels we want to detect. Odd zones represent
    # unstable states corresponding to samples within the hysteresis transition bands.

    #h_t = <double *>malloc((len(hyst_thresholds)) * cython.sizeof(float))
    #if h_t is NULL: raise MemoryError()

    # Copy the thresholds from list to array
    for i in xrange(len(hyst_thresholds)):
        h_t[i] = hyst_thresholds[i]
    
    for sc in samples:
        t = sc.start_time
        sample_period = sc.sample_period
        chunk = sc.samples

        if state == ES_START: # Set initial edge state
            center_ix = len(center_thresholds)
            for i in xrange(center_ix):
                if chunk[0] <= center_thresholds[i]:
                    center_ix = i
                    break

            initial_state = (t, center_ix - zone_offset)
            prev_stable = initial_state[1]
            yield initial_state


        edges = _cy_find_multi_edges(chunk, t, sample_period, h_t, len(hyst_thresholds), &state, &prev_stable)

        for e in edges:
            yield e

    #free(h_t)


@cython.boundscheck(False)
cdef _cy_find_multi_edges(double[:] chunk, double t, double sample_period, double *hyst_thresholds, int h_t_len, \
    int *p_state, int *p_prev_stable):

    cdef int zone, zone_offset, zone_is_stable
    cdef double sample
    cdef unsigned int i, j
    cdef int state, prev_stable

    edges = []
    
    state = p_state[0]
    prev_stable = p_prev_stable[0]

    zone_offset = h_t_len // 4

    #for sample in chunk:
    for i in xrange(chunk.shape[0]):
        sample = chunk[i]
        zone = h_t_len
        for j in xrange(h_t_len):
            if sample <= hyst_thresholds[j]:
                zone = j
                break
        zone_is_stable = zone % 2 == 0
        
        if state == ES_START:
            # Stay in start until we reach one of the stable states
            if zone_is_stable:
                state = zone

        else:
            if state % 2 == 0: # last zone was a stable state
                if zone_is_stable:
                    if zone != state:
                        state = zone
                        edges.append((t, zone // 2 - zone_offset)) #zone_to_logic_state(zone))
                else:
                    prev_stable = state
                    state = zone
            
            else: # last zone was a transitional state (in hysteresis band)
                if zone_is_stable:
                    if zone != prev_stable: # This wasn't just noise
                        edges.append((t, zone // 2 - zone_offset)) #zone_to_logic_state(zone))

                state = zone

        t += sample_period

    p_state[0] = state
    p_prev_stable[0] = prev_stable

    return edges

