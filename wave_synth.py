#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Protocol decode library
   General routines for synthesizing basic waveforms
'''

# Copyright © 2012 Kevin Thibedeau

# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:

# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import print_function, division


import math


def sine_synth(frequency=1.0e6, phase=0.0, sample_period=50.0e-9, samples=None):
    ''' Sine generator
        Will generate a continuous stream of samples from a sine wave.
        This generator will terminate if the number of output sampes is specified.
    '''
    angle = phase
    sc = samples if not samples is None else -1
    
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
    
    sc = samples if not samples is None else -1
    
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