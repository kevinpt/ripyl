#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   Data streaming common classes
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

from ripyl.util.enum import Enum


class StreamType(Enum):
    '''Enumeration for stream types'''
    Edges = 0
    Samples = 1

'''Custom exception class for edge and sample streams'''
class StreamError(RuntimeError):
	pass

class AutoLevelError(StreamError):
    def __init__(self, msg='Unable to find avg. logic levels of waveform'):
        StreamError.__init__(self, msg)
    
    
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
        
    @classmethod
    def status_text(cls, status):
        if status == StreamStatus.Ok or status == StreamStatus.Warning or \
            status == StreamStatus.Error:
            
            return StreamStatus(status)
        else:
            return 'unknown <{}>'.format(status)


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


def save_stream(records, fh):
    '''Save a stream to a file
    
    records
        A list of StreamRecord objects
    
    fh
        Either a file-like object or a string file name. If a file handle is
        passed it should have been opened in 'wb' mode.
    '''
    import pickle
    
    # Make sure the stream is not an iterator
    if hasattr(records, '__iter__') and not hasattr(records, '__len__'):
        raise TypeError('records parameter must be a sequence, not an iterator')
    
    
    opened_file = False
    try:
        if len(fh) > 0:
            fh = open(fh, 'wb')
            opened_file = True
    except TypeError:
        # fh isn't a string assume to be an already open handle
        pass
        
    pickle.dump(records, fh, -1)
    
    if opened_file:
        fh.close()


def load_stream(fh):
    '''Restore a stream from a file
    
    fh
        Either a file-like object or a string file name. If a file handle is
        passed it should have been opened in 'rb' mode.
        
    Returns a list of StreamRecord objects
    '''
    import pickle
    opened_file = False
    try:
        if len(fh) > 0:
            fh = open(fh, 'rb')
            opened_file = True
    except TypeError:
        # fh isn't a string assume to be an already open handle
        pass
        
    records = pickle.load(fh)
    
    if opened_file:
        fh.close()
        
    return records
    
    
def merge_streams(records_a, records_b, id_a=0, id_b=1):
    ''' Combine two streams of StreamRecord objects.
    Records with time signatures from each input stream are kept in chronological order.
        
    records_a
        Source records from stream a
        
    records_b
        Source records from stream b
        
    id_a
        stream_id assigned to records from records_a
        
    id_b
        stream_id assigned to records from records_b
        
    Yields a stream of StreamRecord objects.
    '''
            
    cur_ra = None
    cur_rb = None
    
    while True:
        if cur_ra is None: # Get next record a
            try:
                cur_ra = next(records_a)
            except StopIteration:
                # Nothing left to merge
                if cur_rb is not None:
                    cur_rb.stream_id = id_b
                    yield cur_rb
                    
                for r in records_b:
                    r.stream_id = id_b
                    yield r
                break

        if cur_rb is None: # Get next record b
            try:
                cur_rb = next(records_b)
            except StopIteration:
                # Nothing left to merge
                if cur_ra is not None:
                    cur_ra.stream_id = id_a
                    yield cur_ra

                for r in records_a:
                    r.stream_id = id_a
                    yield r
                break

        # Find the time markers
        try:
            ra_time = cur_ra.start_time # StreamSegment
        except AttributeError:
            try:
                ra_time = cur_ra.time # StreamEvent
            except AttributeError: # No time marker
                cur_ra.stream_id = id_a
                yield cur_ra
                cur_ra = None
                continue

        try:
            rb_time = cur_rb.start_time # StreamSegment
        except AttributeError:
            try:
                rb_time = cur_rb.time # StreamEvent
            except AttributeError: # No time marker
                cur_rb.stream_id = id_b
                yield cur_rb
                cur_rb = None
                continue

        # Determine record chronological order
        if ra_time <= rb_time:
            cur_ra.stream_id = id_a
            yield cur_ra
            cur_ra = None
            
        else:
            cur_rb.stream_id = id_b
            yield cur_rb
            cur_rb = None
