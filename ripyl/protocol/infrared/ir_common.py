#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Infrared decoder common utilities
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

from __future__ import print_function

from ripyl.util.enum import Enum
from ripyl.decode import EdgeSequence

class IRConfig(Enum):
    '''Enumeration of configuration settings'''
    IdleHigh = 1  # Polarity settings
    IdleLow = 2


def time_is_nearly(time, expected_value, epsilon):
    '''Check if a time value is approximately equal another

    time (float)
        The time to test

    expected_value (float)
        The value time should be equal to

    epsilon (float)
        The allowed difference between the time values

    Returns bool
    '''
    return abs(time - expected_value) < epsilon

def time_is_at_least(time, expected_value, epsilon):
    '''Check if a time value is greater than another

    time (float)
        The time to test

    expected_value (float)
        The value time should be greater than

    epsilon (float)
        The allowed difference between the time values

    Returns bool
    '''
    return time >= (expected_value - epsilon)



def modulate(edges, carrier_freq, duty_cycle=0.5, polarity=IRConfig.IdleLow):
    '''Modulate an edge stream

    This is a generator function.

    edges (edge stream)
        The edge stream to modulate

    carrier_freq (float)
        The modulation frequency

    duty_cycle (float)
        The duty cycle of the modulation

    polarity (infrared.IRConfig)
        Set the polarity (idle state high or low)

    Yields an edge stream.
    '''

    duty_cycle = max(min(duty_cycle, 1.0), 0.0) # constrain to 0.0 - 1.0

    # Invert edge polarity if idle-high
    if polarity == IRConfig.IdleHigh:
        edges = ((t, 1 - e) for t, e in edges)

    mod_period = (1.0 / carrier_freq)
    high_time = mod_period * duty_cycle
    low_time = mod_period * (1.0 - duty_cycle)

    es = EdgeSequence(edges, mod_period)

    yield (es.cur_time, es.cur_state()) # initial state

    while not es.at_end():
        es.advance_to_edge()

        while es.cur_state() == 1:
            yield (es.cur_time, 1)
            es.advance(high_time)
            yield (es.cur_time, 0)
            es.advance(low_time)

    yield (es.cur_time, es.cur_state()) # final state


def demodulate(edges, carrier_freq, polarity=IRConfig.IdleLow):
    '''Demodulate an edge stream

    This is a generator function.

    You can safely pass an unmodulated stream through this function without alteration

    edges (edge stream)
        The edge stream to modulate

    carrier_freq (float)
        The modulation frequency

    polarity (infrared.IRConfig)
        Set the polarity (idle state high or low)

    Yields an edge stream.
    '''
    # Invert edge polarity if idle-high
    if polarity == IRConfig.IdleHigh:
        edges = ((t, 1 - e) for t, e in edges)

    mod_period = (1.0 / carrier_freq)

    es = EdgeSequence(edges, mod_period)

    yield (es.cur_time, es.cur_state()) # initial state


    if es.cur_state() == 0:
        es.advance_to_edge() # Now it's 1
        yield (es.cur_time, 1)

    prev_state = es.cur_state()
    while not es.at_end():
        ts = es.advance_to_edge()
        if ts > mod_period: # modulation ended on previous edge
            

            if es.cur_state() == 1:
                yield (es.cur_time - ts, 0)
                yield (es.cur_time, 1)

        prev_state = es.cur_state()

    if prev_state == 0:
        yield (es.cur_time - ts, 0)


    yield (es.cur_time, es.cur_state()) # final state

