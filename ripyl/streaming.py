#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Data streaming common classes
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
from ripyl.util.eng import eng_si
import string
import math


class StreamType(Enum):
    '''Enumeration for stream types'''
    Edges = 0
    Samples = 1


class SampleChunk(object):
    ''''Sample stream object
    
    This represents a "chunk" of samples contained in a numpy array
    stored in the samples attribute.

    '''
    def __init__(self, samples, start_time, sample_period):
        self.samples = samples
        self.start_time = start_time
        self.sample_period = sample_period


class StreamError(RuntimeError):
    '''Custom exception class for edge and sample streams'''
    pass

class AutoLevelError(StreamError):
    '''Custom exception class auto-level errors'''
    def __init__(self, msg='Unable to find avg. logic levels of waveform'):
        StreamError.__init__(self, msg)
    
    
class StreamStatus(Enum):
    '''Enumeration for standard stream status codes'''
    Ok = 0
    Warning = 100
    Error = 200

class AnnotationFormat(Enum):
    '''Enumeration of annotation data formats'''
    Hidden = 0      # Invisible text label
    Invisible = 1   # Invisible text label and rectangle
    General = 2     # Generic label format controlled by the default_format attribute of StreamRecord.text()
    String = 3      # The data attribute is treated as a string
    Text = 4        # The data attribute is a sequence of characters to be converted into a string
    Int = 5
    Hex = 6
    Bin = 7
    Enum = 8        # The data attribute is an enumeration value
    Small = 9       # Small plain text


    
class StreamRecord(object):
    '''Base class for protocol decoder output stream objects

    :ivar kind: A string identifying the kind of record

    :ivar status: An integer status code

    :ivar stream_id: A unique numeric stream identifier

    :ivar subrecords: A list of child StreamRecord objects

	'''
    def __init__(self, kind='unknown', status=StreamStatus.Ok):
        self.kind = kind
        self.status = status
        self.stream_id = 0 # associate this record from multiplexed data with a particular stream
        self.subrecords = []
        self.data_format = AnnotationFormat.Hidden
        self.style = None
        self.fields = {}

    def nested_status(self):
        '''Returns the highest status value from this record and its subrecords'''
        cur_status = self.status
        for srec in self.subrecords:
            nstat = srec.nested_status()
            cur_status = nstat if nstat > cur_status else cur_status
            
        return cur_status

    def annotate(self, style=None, fields=None, data_format=AnnotationFormat.General):
        ''''Set annotation attributes

        style (string or None)
            The name of a style to use for drawing a rectangle representing this record
            (as defined in ripyl.util.plot.annotation_styles)

        fields (dict of string:value)
            A set of arbitrary info fields that may be displayed as attributes of this record.
            The special field '_bits' identifies the number of data bits in this record
            The special field '_enum' identifies an enumeration type for this record's data attribute
            The special field 'value' is a string that will override any other source of label text

        data_format (AnnotationFormat)
            The format for the text label
        '''
        self.style = style
        self.data_format = data_format
        if fields is not None:
            self.fields = fields

        return self

    def text(self, default_format=AnnotationFormat.String):
        '''Generate a string representation of this segment's data

        default_format (AnnotationFormat)
            Set the format to use when the data_format attribute is General
        '''
        if self.data is None or self.data_format == AnnotationFormat.Hidden \
            or self.data_format == AnnotationFormat.Invisible:
            return ''

        if self.data_format == AnnotationFormat.General:
            data_format = default_format
        else:
            data_format = self.data_format

        #print('## text:', AnnotationFormat(data_format), self.fields.keys(), str(self.data))

        if '_value' in self.fields and (data_format in [AnnotationFormat.String, AnnotationFormat.Small, AnnotationFormat.Enum]):
            return str(self.fields['_value'])

        if data_format in [AnnotationFormat.String, AnnotationFormat.Small]:
            return str(self.data)
        elif data_format == AnnotationFormat.Enum and '_enum' in self.fields:
            return self.fields['_enum'](self.data)
    

        if hasattr(self.data, '__len__'):
            data = self.data
        else:
            data = (self.data,)

        words = []
        for d in data:
            if data_format == AnnotationFormat.Int:
                words.append(str(d))
            elif data_format == AnnotationFormat.Hex:
                # If the '_bits' field is present we will compute the number of nibbles needed
                # to display in hex
                if '_bits' in self.fields:
                    nibbles = int(math.ceil(self.fields['_bits'] / 4.0))
                else: # Default to 2 nibbles (may leave an extraneous leading 0)
                    nibbles = 2
                words.append('16#{:0{}X}#'.format(d, nibbles))
            elif data_format == AnnotationFormat.Text:
                try:
                    char = chr(d)
                except ValueError:
                    char = chr(0)

                if char not in string.printable:
                    char = '16#{:02X}#'.format(d)
                words.append(char)
            else:
                words.append('?')

        if data_format == AnnotationFormat.Text:
            return ''.join(words)
        else:
            return ' '.join(words)

        
    @classmethod
    def status_text(cls, status):
        '''Returns the string representation of a status code'''
        if status == StreamStatus.Ok or status == StreamStatus.Warning or \
            status == StreamStatus.Error:
            
            return StreamStatus(status)
        else:
            return 'unknown <{}>'.format(status)


    def __repr__(self):
        return 'StreamRecord(\'{0}\')'.format(self.kind)

    def __eq__(self, other):
        match = True
        if self.kind != other.kind: match = False
        if self.status != other.status: match = False
        if self.stream_id != other.stream_id: match = False
        if len(self.subrecords) != len(other.subrecords):
            match = False
        else:
            for s, o in zip(self.subrecords, other.subrecords):
                if s != o:
                    match = False
                    break

        return match
                

    def __ne__(self, other):
        return not self == other

    
class StreamSegment(StreamRecord):
    '''A stream element that spans two points in time'''
    def __init__(self, time_bounds, data=None, kind='unknown segment', status=StreamStatus.Ok):
        StreamRecord.__init__(self, kind, status)
        self._start_time = time_bounds[0] # (start time, end time)
        self._end_time = time_bounds[1]
        self.data = data

    def __str__(self):
        return self.text()

        
    def __repr__(self):
        return 'StreamSegment(({0},{1}), {2}, \'{3}\')'.format(self.start_time, self.end_time, \
            repr(self.data), self.kind)


    def summary(self, a=None, depth=0):
        '''Yield string(s) summarizing this segment and all of its subrecords
        a (StreamRecord or None)
            StreamRecord to produce summary from. Uses self if None.

        depth (int)
            Indentation level for this summary
        '''
        if a is None:
            a = self

        field_name = ''
        if 'name' in a.fields:
            field_name = '({})'.format(a.fields['name'])

        yield '{}{} - {}: {} {}'.format('  '*depth, eng_si(a.start_time, 's'), eng_si(a.end_time, 's'), a, field_name)
        for sr in a.subrecords:
            for s in self.summary(sr, depth+1):
                yield s


    @property
    def start_time(self):
        return self._start_time

    @start_time.setter
    def start_time(self, value):
        self._start_time = value


    @property
    def end_time(self):
        return self._end_time

    @end_time.setter
    def end_time(self, value):
        self._end_time = value

    def __eq__(self, other):
        match = True
        if not StreamRecord.__eq__(self, other): match = False
        if self.start_time != other.start_time: match = False
        if self.end_time != other.end_time: match = False
        if self.data != other.data: match = False

        return match

    def __ne__(self, other):
        return not self == other


class StreamEvent(StreamRecord):
    '''A stream element that occurs at a specific point in time'''
    def __init__(self, time, data=None, kind='unknown event', status=StreamStatus.Ok):
        StreamRecord.__init__(self, kind, status)
        self.time = time
        self.data = data

    def __repr__(self):
        return 'StreamEvent({0}, {1}, \'{2}\')'.format(self.time, \
            repr(self.data), self.kind)

    def summary(self, a=None, depth=0):
        '''Yield string(s) summarizing this segment and all of its subrecords
        a (StreamRecord or None)
            StreamRecord to produce summary from. Uses self if None.

        depth (int)
            Indentation level for this summary
        '''
        if a is None:
            a = self

        field_name = ''
        if 'name' in a.fields:
            field_name = '({})'.format(a.fields['name'])

        yield '{}! {}: {} {}'.format('  '*depth, eng_si(a.time, 's'), a, field_name)
        for sr in a.subrecords:
            for s in self.summary(sr, depth+1):
                yield s

    def __eq__(self, other):
        match = True
        if not StreamRecord.__eq__(self, other): match = False
        if self.time != other.time: match = False
        if self.data != other.data: match = False

        return match

    def __ne__(self, other):
        return not self == other



def save_stream(records, fh):
    '''Save a stream of StreamRecord objects to a file
    
    records (StreamRecord sequence)
        The StreamRecord objects to save.
    
    fh (file-like object or a string)
        File to save records to. If a file handle is passed it should have been
        opened in 'wb' mode. If a string is passed it is the name of a file to write to.

    Raises TypeError when records parameter is not a sequence.
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
        # fh isn't a string. Assume to be an already open handle
        pass

    try:
        pickle.dump(records, fh, -1)
    finally:
        if opened_file:
            fh.close()


def load_stream(fh):
    '''Restore a stream of StreamRecord objects from a file
    
    fh (file-like object or a string)
        File to load records from. If a file handle is passed it should have been opened
        in 'rb' mode. If a string is passed it is the name of a file to read from.
        
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

    try:
        records = pickle.load(fh)
    finally:
        if opened_file:
            fh.close()
        
    return records
    
    
def merge_streams(records_a, records_b, id_a=0, id_b=1):
    ''' Combine two streams of StreamRecord objects.
    Records with time signatures from each input stream are kept in chronological order.
        
    records_a (StreamRecord)
        Source records from stream a
        
    records_b (StreamRecord)
        Source records from stream b
        
    id_a (int)
        stream_id assigned to records from records_a
        
    id_b (int)
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


import numpy as np

class ChunkExtractor(object):
    '''Utility class that pulls arbitrarily sized chunks from a sample stream'''
    def __init__(self, stream):
        self.stream = stream
        self.sample_buf = []
        self.buf_count = 0
        self.stream_ended = False
        self.buf_start_time = 0.0
        self.sample_period = 0.0

    def next_chunk(self, chunk_size=10000):
        '''Get a new chunk of samples from the stream

        chunk_size (int)
            The number of samples for this chunk.

        Returns a SampleChunk object. If the stream had fewer than chunk_size samples
          remaining then the SampleChunk.samples array is sized to hold only those samples.

        Returns None if the stream has ended.
        '''
        if self.stream_ended:
            return None

        while True:
            if self.buf_count < chunk_size: # Need to get another chunk
                try:
                    sc = next(self.stream)
                    if len(self.sample_buf) == 0:
                        self.buf_start_time = sc.start_time
                        self.sample_period = sc.sample_period
                    self.sample_buf.append(sc.samples)
                    self.buf_count += len(sc.samples)

                except StopIteration:
                    self.stream_ended = True

            if self.stream_ended and self.buf_count < chunk_size:
                # Not enough samples in buffer for a full sized chunk
                chunk_size = self.buf_count
                if chunk_size == 0:
                    break

            if self.buf_count >= chunk_size:
                # We have enough buffered samples to return a new chunk
                out_samp = np.empty(chunk_size, dtype=float)
                out_count = 0
                for b in self.sample_buf:
                    if out_count + len(b) <= chunk_size:
                        use_count = len(b)
                    else:
                        use_count = chunk_size - out_count

                    out_samp[out_count:out_count + use_count] = b[:use_count]
                    out_count += use_count

                out_time = self.buf_start_time

                if self.buf_count > chunk_size:
                    # There are unused samples remaining in the buffer
                    # Place these at the start of the buffer for the next call to next_chunk()
                    self.sample_buf = [self.sample_buf[-1][use_count:]]
                    self.buf_count = len(self.sample_buf[0])
                    self.buf_start_time = self.buf_start_time + self.sample_period * chunk_size
                else:
                    self.sample_buf = []
                    self.buf_count = 0

                return SampleChunk(out_samp, out_time, self.sample_period)

            if self.stream_ended:
                break

        return None

    def next_samples(self, sample_count=10000):
        '''Get a new set of raw samples from the stream

        sample_count (int)
            The number of samples for the array.

        Returns a numpy array of float. If the stream had fewer than sample_count samples
          remaining then the array is sized to hold only those samples.

        Returns None if the stream has ended.
        '''

        sc = self.next_chunk(sample_count)
        if sc is not None:
            return sc.samples
        else:
            return None

    def buffered_chunk(self):
        '''Get all remaining buffered samples'''
        return self.next_chunk(self.buf_count)


def rechunkify(samples, chunk_size=10000):
    '''Create a new gerator that yields SampleChunk objects of the desired size

    This is a generator function. Its send() method can be used to change the
    value of chunk_size mid-stream.

    samples (iterable of SampleChunk objects)
        The sample stream to extract SampleChunk objects from.

    chunk_size (int)
        The number of samples for the SampleChunk objects.


    Yields a series of SampleChunk objects. If the stream has fewer than chunk_size samples
      remaining then the SampleChunk.samples array is sized to hold only those samples.
    '''

    extractor = ChunkExtractor(samples)

    while True:
        sc = extractor.next_chunk(chunk_size)
        if sc is None:
            break

        next_cs = yield sc
        if next_cs is not None:
            chunk_size = next_cs


def extract_samples(samples, sample_count=10000):
    '''Create a new gerator that yields sample arrays of the desired size

    This is a generator function. Its send() method can be used to change the
    value of sample_count mid-stream.

    samples (iterable of SampleChunk objects)
        The sample stream to extract samples from.

    sample_count (int)
        The number of samples for the arrays.

    Yields a series of numpy arrays. If the stream has fewer than sample_count samples
      remaining then the array is sized to hold only those samples.
    '''

    extractor = ChunkExtractor(samples)

    while True:
        s = extractor.next_samples(sample_count)
        if s is None:
            break

        next_sc = yield s
        if next_sc is not None:
            sample_count = next_sc


def extract_all_samples(samples):
    '''Get all samples from a sample stream along with parameter information.

    samples (iterable of SampleChunk objects)
        The sample stream to extract samples from.

    Returns a tuple containing a numpy sample array of float, the start time,
      and the sample period.
    '''

    chunk_buf = [s for s in samples]
    total_samples = sum(len(s.samples) for s in chunk_buf)

    all_samples = np.empty(total_samples, dtype=float)
    offset = 0
    for s in chunk_buf:
        all_samples[offset:offset+len(s.samples)] = s.samples
        offset += len(s.samples)

    return all_samples, chunk_buf[0].start_time, chunk_buf[0].sample_period


def sample_stream_to_samples(samples):
    '''Get all samples from a sample stream as an array

    samples (iterable of SampleChunk objects)
        The sample stream to extract samples from.

    Returns a numpy array of float.
    '''

    return extract_all_samples(samples)[0]
    
    

def samples_to_sample_stream(raw_samples, sample_period, start_time=0.0, chunk_size=10000):
    '''Convert raw samples to a chunked sample stream

    This is a generator function that can be used in a pipeline of waveform
    procesing operations

    raw_samples (iterable of numbers)
        The samples to convert to a sample stream.
    
    sample_period (float)
        The time interval between samples

    start_time (float)
        The time for the first sample

    chunk_size (int)
        The maximum number of samples for each chunk

    Yields a series of SampleChunk objects representing the time and
      sample value for each input sample. This can be fed to functions
      that expect a chunked sample stream as input.
    '''
    t = start_time
    for i in xrange(0, len(raw_samples), chunk_size):
        chunk = np.asarray(raw_samples[i:i + chunk_size], dtype=float)
        sc = SampleChunk(chunk, t, sample_period)

        yield sc
        t += sample_period * len(chunk)

