#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   Data streaming common classes
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

from util.enum import Enum


class StreamType(Enum):
    '''Enumeration for stream types'''
    Edges = 0
    Samples = 1

'''Custom exception class for edge and sample streams'''
class StreamError(RuntimeError):
	pass

    
    
class StreamStatus(Enum):
    '''Enumeration for standard stream status codes'''
    Ok = 0
    Warning = 100
    Error = 200
    
class StreamRecord(object):
    '''Base class for protocol decoder output stream objects'''
    def __init__(self, kind='unknown', status=StreamStatus.Ok):
        self.kind = kind
        self.status = status
        self.stream_id = 0 # associate this record from multiplexed data with a particular stream
        self.subrecords = []

    def nested_status(self):
        '''Retrieve the highest status value from this record and its subrecords'''
        cur_status = self.status
        for srec in self.subrecords:
            nstat = srec.nested_status()
            cur_status = nstat if nstat > cur_status else cur_status
            
        return cur_status

    def __repr__(self):
        return 'StreamRecord(\'{0}\')'.format(self.kind)
    
class StreamSegment(StreamRecord):
    '''A stream element that spans two points in time'''
    def __init__(self, time_bounds, data=None, kind='unknown segment', status=StreamStatus.Ok):
        StreamRecord.__init__(self, kind, status)
        self.start_time = time_bounds[0] # (start time, end time)
        self.end_time = time_bounds[1]
        self.data = data
        
    def __repr__(self):
        return 'StreamSegment(({0},{1}), {2}, \'{3}\')'.format(self.start_time, self.end_time, \
            repr(self.data), self.kind)

class StreamEvent(StreamRecord):
    '''A stream element that occurs at a specific point in time'''
    def __init__(self, time, data=None, kind='unknown event', status=StreamStatus.Ok):
        StreamRecord.__init__(self, kind, status)
        self.time = time
        self.data = data

    def __repr__(self):
        return 'StreamEvent({0}, {1}, \'{2}\')'.format(self.time, \
            repr(self.data), self.kind)
