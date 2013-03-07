#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Protocol decode library
   General routines for synthesizing basic waveforms
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


import math


def sine_synth(frequency=1.0e6, phase=0.0, sample_period=50.0e-9, samples=None):
    ''' Sine generator
        Will generate a continuous stream of samples from a sine wave.
        This generator will terminate if the number of output sampes is specified.
    '''
    angle = phase
    sc = samples if samples is not None else -1
    
    while sc > 0 or sc < 0:
        s = math.sin(angle)
        angle += 2.0 * math.pi * frequency * sample_period
        angle %= 2.0 * math.pi
        
        if sc > 0:
            sc -= 1
        yield s
        
def square_synth(frequency=1.0e6, duty=0.5, phase=0.0, sample_period=50.0e-9, samples=None):
    ''' Square wave generator
    '''
    
    sc = samples if samples is not None else -1
    
    period = 1.0 / frequency
    fe_time = duty / frequency
    
    t = phase * period
    cur_level = 1 if t < fe_time else 0
    
    while sc > 0 or sc < 0:
        t += sample_period
        if t > fe_time and cur_level == 1:
            cur_level = 0
            
        if t > period:
            t -= period
            cur_level = 1
            
        if sc > 0:
            sc -= 1
            
        yield cur_level