#!/usr/bin/python
# -*- coding: utf-8 -*-

'''ISO K-line protocol decoder

   Decodes ISO9141 and ISO14230 automotive data bus protocols
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

from ripyl.decode import *
import ripyl.streaming as stream
import ripyl.sigproc as sigp
from ripyl.util.enum import Enum
import ripyl.protocol.uart as uart
import ripyl.protocol.obd2 as obd


# I have encountered an ECU (Sagem MC1000) that is largely ISO9141 based but
# also responds to an ISO14230 command for ECU identification after a special init
# phase. For that reason this decoder supports both message formats simultaneously.

# We use bit-7 of the first header byte to determine the protocol.
# 0 = ISO9141, 1 = ISO14230

# Another option for detecting the protocol is the key bytes in the init sequence (ISO9141)
# or in the response to the StartCommunication request. (ISO14230)
# ISO9141 keys : 08 08; 94 94
# ISO14230 keys: 8F E9; 8F 6B; 8F 6D; 8F EF

# Unknown key used on Sagem MC1000 for ISO14230 init: D9 8F

# Detecting the length of a message is tricky since ISO9141 doesn't include a byte
# count and we are not monitoring the L-line to differentiate between data sent
# and received. Until a better system can be devised the decoder uses a simple
# minimum time period between bytes to decide if a new message has started.
# The OBD-2 standard requires this to be at least 55ms but This can be violated by
# the tool controlling the interface. In one case, a piece of software had a gap
# as low as 8ms between messages.

# ISO14230 messages are terminated at the length indicated in their header.

# Messages are either a request from an external tool or a response from one or
# more ECUs. These are distinguished by looking at the value of the service ID (mode)
# in the message. This is the first data byte after the header.
# SIDs from 0x00 to 0x3F are requests. SIDs from 0x40 to 0x7F are responses.



class KLineProtocol(Enum):
    '''Enumeration for identifying the message protocol'''
    Unknown = 0
    ISO9141 = 1
    ISO14230 = 2 # KWP2000


class KLineStreamStatus(Enum):
    '''Enumeration for KLineStreamMessage status codes'''
    ChecksumError = stream.StreamStatus.Error + 1
    BadInitError = stream.StreamStatus.Error + 2
    InvalidMessageError = stream.StreamStatus.Error + 3

class ISO9141Header(object):
    '''ISO9141 header object

    Header byte 1: option

    |   7-5 priority: 000 = high, 111 = low
    |   4   header type: 0 = 3-byte; 1 = 1-byte
    |   3   in frame response: 0 = required (Ford); 1 = not allowed (GM)
    |   2   addressing mode: 1 = physical; 0 = functional
    |   1-0 message type
    |
    |  message type:
    |  bit: 3 2 1 0
    |       -------
    |       1 0 0 0 function
    |       1 0 0 1 broadcast
    |       1 0 1 0 query
    |       1 0 1 1 read
    |       1 1 0 0 node-to-node
    |       1 1 0 1 reserved
    |       1 1 1 0 reserved
    |       1 1 1 1 reserved
    |       

    Header byte 2: target address
    Header byte 3: source address
    '''
    def __init__(self, option, target, source):
        '''
        option, target, source
            USBFrame objects for the header bytes
        '''
        self.option = option
        self.target = target
        self.source = source

    def bytes(self):
        '''Returns a list of header bytes in original order'''
        return [self.option, self.target, self.source]


    def __repr__(self):
        return 'ISO9141Header({:02x}, {:02x}, {:02x})'.format(self.option.data, self.target.data, \
            self.source.data)

    def __str__(self):
        return '[{:02x} {:02x} {:02x}]'.format(self.option.data, self.target.data, self.source.data)


class ISO14230Header(object):
    '''ISO14230 header object

    Header byte 1: length 0x10nnnnnn
        5-0 data bytes in message

    Header byte 2: optional data byte count if nnnnnn is 0

    Header byte 2(3): target address
    Header byte 3(4): source address
    '''
    def __init__(self, option, target, source, length=None):
        '''
        option, target, source, length
            USBFrame objects for the header bytes
        '''
        self.option = option
        self.target = target
        self.source = source
        self.length = length

    def bytes(self):
        '''Returns a list of header bytes in original order'''
        if self.length is None:
            return [self.option, self.target, self.source]
        else:
            return [self.option, self.length, self.target, self.source]

    def __repr__(self):
        if self.length is None:
            rep = 'ISO14230Header({:02x}, {:02x}, {:02x})'.format(self.option.data, self.target.data, \
            self.source.data)
        else:
            rep = 'ISO14230Header({:02x}, {:02x}, {:02x}, {:02x})'.format(self.option.data, \
            self.target.data, self.source.data, self.length.data)

        return rep

    def __str__(self):
        if self.length is None:
            s = '[{:02x} {:02x} {:02x}]'.format(self.option.data, self.target.data, self.source.data)
        else:
            s = '[{:02x} ({:02x}) {:02x} {:02x}]'.format(self.option.data, self.length.data, \
            self.target.data, self.source.data)
        return s



class KLineMessage(obd.OBD2Message):
    '''Message object for the K-line protocols ISO9141 and ISO14230'''
    def __init__(self, msg_type, header, data, checksum):
        obd.OBD2Message.__init__(self, msg_type)
        self.header = header
        self.data = data
        self.checksum = checksum


    def checksum_good(self):
        '''Validate the message checksum

        Returns a bool that is True when checksum is valid.
        '''
        bdata = self.header.bytes() + self.data
        cs = sum([b.data for b in bdata]) % 256

        return True if cs == self.checksum.data else False

    def raw_data(self, full_message=False):
        '''Get the raw data for the message

        full_message (bool)
            Returns complete message including header and checksum when true

        Returns a list of bytes.
        '''
        if full_message:
            return [b for a in [[b.data for b in self.header.bytes()], \
                [b.data for b in self.data], [self.checksum.data]] for b in a]
        else:
            return [b.data for b in self.data]


    @property
    def start_time(self):
        return self.header.option.start_time

    @property
    def end_time(self):
        return self.checksum.end_time


    def __repr__(self):
        return 'KLineMessage({}, {}, {}, {:02x}'.format(obd.OBD2MsgType(self.msg_type), \
            self.header, [hex(b.data) for b in self.data], self.checksum.data)

    def __str__(self):
        mtype = 'req >' if self.msg_type == obd.OBD2MsgType.Request else 'resp <'
        data_bytes = ' '.join('{:02x}'.format(b.data) for b in self.data)
        cs_flag = '' if self.checksum_good() else ' BAD checksum!'

        return '{:>6} {} {} <{:02x}{}> '.format(mtype, self.header, data_bytes, self.checksum.data, cs_flag)


class KLineStreamMessage(obd.OBD2StreamMessage):
    '''StreamMessage object for the K-line protocols ISO9141 and ISO14230'''
    def __init__(self, msg, status=stream.StreamStatus.Ok):
        obd.OBD2StreamMessage.__init__(self, msg, status)

    @classmethod
    def status_text(cls, status):
        '''Returns the string representation of a status code'''
        if status >= KLineStreamStatus.ChecksumError and \
            status <= KLineStreamStatus.ChecksumError:
            
            return KLineStreamStatus(status)
        else:
            return obd.OBD2StreamMessage.status_text(status)

    def __repr__(self):
        status_text = KLineStreamMessage.status_text(self.status)
        return 'KLineStreamMessage({}, {})'.format(self.msg, status_text)




class KLineWakeup(stream.StreamSegment):
    '''Encapsulates BRK data values representing the wakeup pattern
    
    This is used for the slow init (0x33 at 5-baud) and the fast init (25ms low, 25ms high)
    ''' 
    def __init__(self, bounds, edges, status=stream.StreamStatus.Ok):
        stream.StreamSegment.__init__(self, bounds, None, status)
        self.data = edges

        self.kind = 'K-line wakeup'

    def __repr__(self):
        status_text = stream.StreamSegment.status_text(self.status)
        return 'KLineWakeup({})'.format(status_text)


class ISO9141Init(stream.StreamSegment):
    '''Encapsulates initialization exchange before messaging begins on ISO9141
    These are the bytes in the 0x55, key1, key2, ~key2 ~wakeup init sequence.
    ''' 
    def __init__(self, recs, status=stream.StreamStatus.Ok):
        bounds = (recs[0].start_time, recs[-1].end_time)
        stream.StreamSegment.__init__(self, bounds, status)
        self.annotate('frame', {}, stream.AnnotationFormat.Hidden)
        for r in recs:
            self.subrecords.append(r.subrecords[1])
            self.subrecords[-1].annotate('ctrl', {}, stream.AnnotationFormat.General)

        self.kind = 'ISO9141 init'

    def __repr__(self):
        status_text = stream.StreamSegment.status_text(self.status)
        return 'ISO9141Init({})'.format(status_text)



def iso_k_line_decode(stream_data, min_message_interval=7.0e-3, logic_levels=None, stream_type=stream.StreamType.Samples):
    '''Decode ISO9141 and ISO14230 data streams

    This is a generator function that can be used in a pipeline of waveform
    procesing operations.

    Sample streams are a sequence of SampleChunk Objects. Edge streams are a sequence
    of 2-tuples of (time, int) pairs. The type of stream is identified by the stream_type
    parameter. Sample streams will be analyzed to find edge transitions representing
    0 and 1 logic states of the waveforms. With sample streams, an initial block of data
    is consumed to determine the most likely logic levels in the signal.

    stream_data (iterable of SampleChunk objects or (float, int) pairs)
        A sample stream or edge stream of K-line messages.

    min_message_interval (float)
        The minimum time between bytes for identifying the end and start
        of messages. For ISO14230 this is used in addition to the message length encoded
        in the header.
    
    logic_levels ((float, float) or None)
        Optional pair that indicates (low, high) logic levels of the sample
        stream. When present, auto level detection is disabled. This has no effect on
        edge streams.
    
    stream_type (streaming.StreamType)
        A StreamType value indicating that the stream parameter represents either Samples
        or Edges
        
        
    Yields a series of KLineStreamMessage objects.
      
    Raises AutoLevelError if stream_type = Samples and the logic levels cannot
      be determined.
    '''

    if stream_type == stream.StreamType.Samples:
        if logic_levels is None:
            samp_it, logic_levels = check_logic_levels(stream_data)
        else:
            samp_it = stream_data
        
        edges = find_edges(samp_it, logic_levels, hysteresis=0.4)
    else: # the stream is already a list of edges
        edges = stream_data

    bits = 8
    parity = None
    stop_bits = 1
    polarity = uart.UARTConfig.IdleHigh
    baud_rate = 10400

    records_it = uart.uart_decode(edges, bits, parity, stop_bits, lsb_first=True, \
        polarity=polarity, baud_rate=baud_rate, logic_levels=logic_levels, stream_type=stream.StreamType.Edges)

    S_WAKEUP  = 0
    S_INIT    = 1
    S_START_MSG = 2
    S_GET_MSG = 3


    state = S_GET_MSG
    wakeup_edges = []
    init_bytes = []
    protocol = KLineProtocol.Unknown
    msg_bytes = []
    prev_byte_end = 0.0
    total_length = None

    def get_msg_len(msg_bytes):
        # Try to determine message length
        if len(msg_bytes) > 0:
            if msg_bytes[0].data & 0x80: #ISO14230
                # Get length from first byte
                length = msg_bytes[0].data & 0x3F
                total_length = 3 + length + 1
                if length == 0: # Header is 4-bytes long
                    if len(msg_bytes) >= 2: # 2nd byte is present
                        length = msg_bytes[1].data
                        total_length = 4 + length + 1
                    else:
                        return None
                return total_length

            else: #ISO9141
                return None
        else:
            return None

    def build_msg(protocol, msg_bytes):
        # determine header length
        header_length = 3
        if protocol == KLineProtocol.ISO14230 and msg_bytes[0].data == 0x80:
            header_length = 4

        # Message must be at least h_l + 1 + 1 = 5 or 6 bytes long
        if len(msg_bytes) >= header_length + 2:

            sid_byte = msg_bytes[header_length]
            msg_type = obd.OBD2MsgType.Request if sid_byte.data <= 0x3F else obd.OBD2MsgType.Response

            if protocol == KLineProtocol.ISO9141:
                header = ISO9141Header(option=msg_bytes[0], target=msg_bytes[1], source=msg_bytes[2])
            elif protocol == KLineProtocol.ISO14230:
                if header_length == 4:
                    length = msg_bytes[1]
                    target = msg_bytes[2]
                    source = msg_bytes[3]
                else:
                    length = None
                    target = msg_bytes[1]
                    source = msg_bytes[2]

                header = ISO14230Header(option=msg_bytes[0], target=target, source=source, \
                    length=length)
            else: # Unknown protocol
                header = ISO9141Header(option=msg_bytes[0], target=msg_bytes[1], source=msg_bytes[2])

            msg = KLineMessage(msg_type, header, msg_bytes[header_length:-1], msg_bytes[-1])

            status = KLineStreamStatus.ChecksumError if not msg.checksum_good() else stream.StreamStatus.Ok
            obd_msg = KLineStreamMessage(msg, status)
            obd_msg.annotate('frame', {}, stream.AnnotationFormat.Hidden)
            for b in msg_bytes:
                obd_msg.subrecords.append(b.subrecords[1])
                obd_msg.subrecords[-1].annotate('data', {'_bits':8}, stream.AnnotationFormat.General)
                obd_msg.subrecords[-1].kind = 'data'

            for sr in obd_msg.subrecords[0:header_length]:
                sr.style = 'addr'
                sr.kind = 'header'

            obd_msg.subrecords[-1].style = 'check'
            obd_msg.subrecords[-1].status = status
            obd_msg.subrecords[-1].kind = 'checksum'

        else:
            # Not enough bytes for proper K-line message
            msg = KLineMessage(obd.OBD2MsgType.Unknown, None, msg_bytes, None)
            obd_msg = KLineStreamMessage(msg, KLineStreamStatus.InvalidMessageError)
            for b in msg_bytes:
                obd_msg.subrecords.append(b.subrecords[1])
                obd_msg.subrecords[-1].annotate('misc', {'_bits':8}, stream.AnnotationFormat.General)



        return obd_msg


    for r in records_it:

        if r.data == 0x00 and r.status == uart.UARTStreamStatus.FramingError:
            state = S_WAKEUP
            wakeup_edges.append(r.start_time)

            continue

        if state == S_WAKEUP:
            if not (r.data == 0x00 and r.status == uart.UARTStreamStatus.FramingError):
                # not a BRK byte; wakeup has ended
                bounds = (wakeup_edges[0], r.start_time)
                wu = KLineWakeup(bounds, wakeup_edges)
                wu.annotate('frame', {}, stream.AnnotationFormat.Hidden)
                yield wu
                wakeup_edges = []

                if r.data == 0x55: # ISO9141 sync byte
                    protocol = KLineProtocol.ISO9141
                    init_bytes.append(r)
                    init_bytes_left = 4
                    state = S_INIT

                elif r.data == 0xc1: # KWP2000 start comm. format byte
                    protocol = KLineProtocol.ISO14230
                    msg_bytes.append(r)
                    state = S_GET_MSG
                    prev_byte_end = r.end_time
                else: # Unexpected data
                    se = stream.StreamEvent(r.start_time, kind='Bad init', \
                        status=KLineStreamStatus.BadInitError)
                    yield se

                    # We will just assume this is the start of a new message
                    msg_bytes.append(r)
                    state = S_GET_MSG
                    prev_byte_end = r.end_time


        elif state == S_INIT:
            # After 0x55 there are 4 more bytes remaining in the init sequence
            # Key 1, Key 2, ~Key 2, ~Wakeup (0xCC typ.)
            init_bytes.append(r)
            init_bytes_left -= 1

            if init_bytes_left == 0:
                yield ISO9141Init(init_bytes)
                init_bytes = []

                state = S_START_MSG
                prev_byte_end = r.end_time

        elif state == S_START_MSG:
            protocol =  KLineProtocol.ISO14230 if r.data & 0x80 else KLineProtocol.ISO9141
            msg_bytes.append(r)
            state = S_GET_MSG
            prev_byte_end = r.end_time

        elif state == S_GET_MSG:
            if len(msg_bytes) == 2:
                total_length = get_msg_len(msg_bytes)

            #print('### byte:', eng.eng_si(r.start_time, 's'), \
            #    eng.eng_si(r.start_time - prev_byte_end, 's'), hex(r.data))
            if (r.start_time - prev_byte_end > min_message_interval and len(msg_bytes) > 0) or \
                (total_length is not None and len(msg_bytes) == total_length):
                # Previous message ended
                msg = build_msg(protocol, msg_bytes)
                yield msg
                msg_bytes = []
                total_length = None

                # Determine the protocol of the next message
                protocol =  KLineProtocol.ISO14230 if r.data & 0x80 else KLineProtocol.ISO9141


            msg_bytes.append(r)
            prev_byte_end = r.end_time

    # Handle final message
    if len(msg_bytes) > 0:
        msg = build_msg(protocol, msg_bytes)
        yield msg
        msg_bytes = []

    # There may have been a partial wakeup pattern at the end of the stream
    if len(wakeup_edges) > 0:
        bounds = (wakeup_edges[0], prev_byte_end)
        wu = KLineWakeup(bounds, wakeup_edges)
        wu.annotate('frame', {}, stream.AnnotationFormat.Hidden)
        yield wu


def iso_k_line_synth(messages, idle_start=0.0, message_interval=8.0e-3, idle_end=0.0, word_interval=1.0e-3):
    '''Generate synthesized ISO9141 and ISO14230 data streams
    
    messages (sequence of tuple of int)
        Messages to be synthesized. Each element is a tuple of bytes to send
        for each message.

    idle_start (float)
        The amount of idle time before the transmission of messages begins.

    message_interval (float)
        The amount of time between messages.
    
    idle_end (float)
        The amount of idle time after the last message.

    word_interval (float)
        The amount of time between message bytes.

    Yields an edge stream of (float, int) pairs. The first element in the iterator
      is the initial state of the stream.
    '''

    msg_its = []
    for i, msg in enumerate(messages):
        istart = idle_start if i == 0 else 0.0
        iend = idle_end if i == len(messages)-1 else 0.0
        msg_its.append(uart.uart_synth(msg, bits=8, baud=10400, idle_start=istart, \
            idle_end=iend, word_interval=word_interval))

    return sigp.chain_edges(message_interval, *msg_its)


