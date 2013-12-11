#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Manchester encoding utilities
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

import ripyl.decode as decode
from ripyl.util.enum import Enum

class ManchesterStates(Enum):
    '''Enumeration of manchester states'''
    Zero = 0 # 0 for 1 bit period
    One =  1 # 1 for 1 bit period
    Low =  2 # Low for half bit period
    High = 3 # High for half bit period
    Idle = 4 # Differential idle state



def manchester_decode(edges, bit_period, falling=0, combine_bits=False):
    '''Convert differential coded edges to manchester states

    edges (iterable of (float, int))
        An edge stream of differential states (-1, 0, 1) representing Manchester
        coded bits.

    bit_period (float)
        The period of a single bit.

    falling (int)
        The bit encoding for a falling edge. Either 0 or 1.

    combine_bits (bool)
        When True, the output states will only be yielded when a different state
        occurs. When False, a state is yielded for each bit or half-bit.

    Yields a stream of Manchester states in (float, int) form.
    '''

    def to_manchester(diff_state):
        '''Utility function to convert differentially coded states to ManchesterStates'''
        if diff_state == 1:
            mstate = ManchesterStates.High
        elif diff_state == -1:
            mstate = ManchesterStates.Low
        else:
            mstate = ManchesterStates.Idle

        return mstate

    es = decode.EdgeSequence(edges, bit_period)

    # Initial state
    yield (es.cur_time, to_manchester(es.cur_state()))

    processing_bits = False
    prev_bit = None

    while not es.at_end():
        if not processing_bits: #state == S_IDLE:
            es.advance_to_edge()

            if es.cur_state() in (1, -1):
                es.advance(bit_period * 0.25)
                processing_bits = True
                prev_bit = None
            else:
                yield (es.cur_time, ManchesterStates.Idle)


        else: # processing bits
            if es.cur_state() not in (1, -1): # Idle
                yield (es.cur_time - bit_period*0.25, ManchesterStates.Idle)
                processing_bits = False

            elif es.next_states[0] - es.cur_time < bit_period * 0.5: # This is a bit
                if es.next_states[1] == 1: # rising edge
                    bit = 1 - falling
                elif es.next_states[1] == -1: # falling edge
                    bit = falling
                else: # Unexpected transition to idle
                    # Create a half bit for this segment
                    yield (es.cur_time - bit_period*0.25, to_manchester(es.cur_state()))
                    es.advance(bit_period * 0.5)
                    continue

                #print('### got bit 2:', bit, prev_bit, es.cur_time - bit_period*0.25)
                if not combine_bits or bit != prev_bit:
                    yield (es.cur_time - bit_period*0.25, bit)

                prev_bit = bit
                es.advance(es.next_states[0] - es.cur_time + bit_period*0.75) # Resync to next edge

            else: # This is a half bit
                #print('## half bit 2', es.cur_time - bit_period*0.25)
                half_bit = to_manchester(es.cur_state())
                if not combine_bits or half_bit != prev_bit:
                    yield (es.cur_time - bit_period*0.25, half_bit)

                prev_bit = half_bit
                es.advance(bit_period * 0.5)


def manchester_encode(states, bit_period, falling=0, idle_start=0.0, idle_end=0.0):
    '''Convert Manchester states to a stream of unipolar (0, 1, Idle) states

    states (iterable of ManchesterState)
        A series of ManchesterStates to encode.

    bit_period (float)
        The period of a single bit.

    falling (int)
        The bit encoding for a falling edge. Either 0 or 1.

    idle_start (float)
        The amount of idle time before the transmission of states begins.

    idle_end (float)
        The amount of idle time after the last state.

    Yields an edge stream of encoded states including Idle.
    '''
    
    t = 0.0

    if falling == 0:
        zero = (1, 0)
        one = (0, 1)
    else:
        zero = (0, 1)
        one = (1, 0)

    half_bit_period = bit_period / 2

    yield (t, ManchesterStates.Idle) # Set initial conditions
    t += idle_start


    prev_state = ManchesterStates.Idle

    for s in states:
        if s <= 1: # 0 or 1
            if s == 0:
                if zero[0] != prev_state:
                    yield (t, zero[0])
                t += half_bit_period
                yield (t, zero[1])
                prev_state = zero[1]
            else: # 1
                if one[0] != prev_state:
                    yield (t, one[0])
                t += half_bit_period
                yield (t, one[1])
                prev_state = one[1]
            t += half_bit_period

        elif s <= 3: # Low or High
            if s - 2 != prev_state:
                yield (t, s - 2)
            prev_state = s - 2
            t += half_bit_period
        else: # Idle
            if ManchesterStates.Idle != prev_state:
                yield (t, ManchesterStates.Idle)
            prev_state = ManchesterStates.Idle
            t += half_bit_period

    if idle_end > 0.0:
        yield (t + idle_end, prev_state)


def diff_encode(bits):
    '''Convert from unipolar Manchester states (0, Idle, 1) to differential (-1, 0, 1) encoding

    bits (iterable of (float, int))
        An edge stream to convert to differential form.

    Yields an edge stream of differentially coded states.
    '''
    for b in bits:
        if b[1] == 1:
            yield b
        elif b[1] == 0:
            yield (b[0], -1)
        else: # Idle
            yield (b[0], 0)


