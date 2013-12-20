#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ethernet protocol decoder
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

import ripyl
import ripyl.decode as decode
import ripyl.sigproc as sigp
import ripyl.streaming as stream
from ripyl.util.enum import Enum
from ripyl.util.bitops import split_bits, join_bits
from ripyl.manchester import manchester_encode, manchester_decode, ManchesterStates, diff_encode
from copy import copy
import itertools
from ripyl.util.eng import eng_si


ethertypes = {
    0x0800:	'IPv4',
    0x0806: 'ARP',
    0x0842: 'Wake-on-LAN',
    0x22F3: 'IETF TRILL Protocol',
    0x6003: 'DECnet Phase IV',
    0x8035: 'Reverse Address Resolution Protocol',
    0x809B: 'AppleTalk',
    0x80F3: 'AppleTalk Address Resolution Protocol',
    0x8100: 'VLAN-tagged frame',
    0x8137: 'IPX',
    0x8138: 'IPX',
    0x8204: 'QNX Qnet',
    0x86DD: 'IPv6',
    0x8808: 'Ethernet flow control',
    0x8809: 'Slow Protocols (IEEE 802.3)',
    0x8819: 'CobraNet',
    0x8847: 'MPLS unicast',
    0x8848: 'MPLS multicast',
    0x8863: 'PPPoE Discovery Stage',
    0x8864: 'PPPoE Session Stage',
    0x8870: 'Jumbo Frame',
    0x887B: 'HomePlug 1.0 MME',
    0x888E: 'EAP over LAN (IEEE 802.1X)',
    0x8892: 'PROFINET',
    0x889A: 'HyperSCSI',
    0x88A2: 'ATA over Ethernet',
    0x88A4: 'EtherCAT Protocol',
    0x88A8: 'Provider Bridging',
    0x88AB: 'Ethernet Powerlink',
    0x88CC: 'LLDP',
    0x88CD: 'SERCOS III',
    0x88E1: 'HomePlug AV MME[citation needed]',
    0x88E3: 'Media Redundancy Protocol (IEC62439-2)',
    0x88E5: 'MAC security (IEEE 802.1AE)',
    0x88F7: 'Precision Time Protocol (IEEE 1588)',
    0x8902: 'IEEE 802.1ag Connectivity Fault Management (CFM)',
    0x8906: 'Fibre Channel over Ethernet (FCoE)',
    0x8914: 'FCoE Initialization Protocol',
    0x8915: 'RDMA over Converged Ethernet (RoCE)',
    0x892F: 'High-availability Seamless Redundancy (HSR)',
    0x9000: 'Ethernet Configuration Testing Protocol',
    0x9100: 'Q-in-Q',
    0xCAFE: 'Veritas Low Latency Transport'
}    

class EthernetTag(object):
    '''Tag object representing 802.1Q tag'''
    def __init__(self, tpid, tci):
        self.tpid = tpid
        self.tci = tci

    def __repr__(self):
        return 'EthernetTag({}, {})'.format(hex(self.tpid), hex(self.tci))

    @property
    def pcp(self):
        return self.tci >> 13

    @property
    def dei(self):
        return self.tci >> 12 & 0x01

    @property
    def vid(self):
        return self.tci & 0xFFF

    @property
    def bytes(self):
        return (self.tpid >> 8 & 0xFF, self.tpid & 0xFF, self.tci >> 8 & 0xFF, self.tci & 0xFF)

    def __eq__(self, other):
        return vars(self) == vars(other)

    def __ne__(self, other):
        return not (self == other)


class MACAddr(object):
    '''Ethernet MAC address'''
    def __init__(self, addr):
        '''
        addr (str or sequence of int)
            The address can be specified as in two formats: a list of int or a string. The string
            is a series of hex digits with optional colon separators on byteboundaries.

        Raises ValueError if the address does not contain 6 bytes.
        '''
        if isinstance(addr, str):
            if ':' in addr:
                self.bytes = [int(b, 16) for b in addr.split(':')]
            else:
                hex_bytes = [addr[i:i+2] for i in xrange(0, len(addr), 2)]
                self.bytes = [int(b, 16) for b in hex_bytes]
        else:
            self.bytes = addr

        if len(self.bytes) != 6:
            raise ValueError('Wrong size for Ethernet MAC address')

    def __getitem__(self, i):
        return self.bytes[i]

    def __len__(self):
        return len(self.bytes)

    def __str__(self):
        return ':'.join('{:02X}'.format(b) for b in self.bytes)

    def __eq__(self, other):
        return vars(self) == vars(other)

    def __ne__(self, other):
        return not (self == other)


class EthernetFrame(object):
    '''Ethernet frame object'''
    # Ethernet II frame: length_type field >= 0x600 (type code)
    # 802.3 frame: length_type field < 0x600 (length code)
    # 802.3 SNAP frame: 802.3 frame + LLC field = 0xaaaa03
    
    def __init__(self, dest, source, data, length_type=None, tags=None, crc=None):
        '''
        dest (MACAddr, str, or sequence of int)
            The destination address of the frame.

        source (MACAddr, str, or sequence of int)
            The source address of the frame.

        data (sequence of int)
            The data for the frame. Padding is not necessary.

        length_type (int or None)
            The Ethertype / length field. Ethertypes should be >= 0x600.

        tags (sequence of EthernetTag or None)
            Optional sequence of 802.1Q tags to insert into frame.

        crc (int or None)
            The decoded CRC for the frame. Leave as None to generate CRC automatically.
        '''
        if not isinstance(dest, MACAddr):
            dest = MACAddr(dest)

        if not isinstance(source, MACAddr):
            source = MACAddr(source)

        self.dest = dest
        self.source = source
        self.tags = tags # 802.1Q and 802.1ad header
        self._length_type = length_type
        self.data = data
        self._crc = crc

    def __repr__(self):
        return 'EthernetFrame("{}", "{}", {}, {}, {}, {})'.format(self.dest, self.source, self.data, \
                hex(self.length_type), self.tags, hex(self.crc))

    @property
    def length_type(self):
        if self._length_type is None:
            return len(self.data)
        else:
            return self._length_type

    @length_type.setter
    def length_type(self, value):
        self._length_type = value & 0xFFFF


    @property
    def crc(self):
        if self._crc is None:
            crc_bytes = self.bytes[-4:]
            crc = 0
            for b in crc_bytes:
                crc <<= 8
                crc += b
            return crc
        else:
            return self._crc

    @crc.setter
    def crc(self, value):
        self._crc = value


    def crc_is_valid(self, recv_crc=None):
        '''Check if a decoded CRC is valid.

        recv_crc (int or None)
            The decoded CRC to check against. If None, the CRC passed in the constructor is used.

        Returns True when the CRC is correct.
        '''
        if recv_crc is None:
            recv_crc = self._crc

        data_crc = 0
        for b in self.bytes[-4:]:
            data_crc <<= 8
            data_crc += b
        
        return recv_crc == data_crc

    @property
    def bytes(self):
        '''Get the bytes for this frame.

        Returns a series of bytes representing the header, payload, and CRC. This does not
        include the SOF and SFD sequence.
        '''
        tag_bytes = []
        if self.tags is not None:
            for t in self.tags:
                tag_bytes.extend(t.bytes)

        len_type_bytes = [self.length_type >> 8 & 0xFF, self.length_type & 0xFF]

        # Add padding for short payloads
        pad_bytes = []
        min_data_size = 42 if len(tag_bytes) >= 4 else 46
        if len(self.data) < min_data_size:
            pad_bytes = [0] * (min_data_size - len(self.data))

        check_bytes = self.dest.bytes + self.source.bytes + tag_bytes + len_type_bytes + self.data + pad_bytes

        crc = table_ethernet_crc32(check_bytes)
        crc_bytes = [0] * 4

        for i in xrange(4):
            crc_bytes[i] = crc & 0xFF
            crc >>= 8

        return check_bytes + crc_bytes


    def bit_stream(self):
        '''Get the sequence of raw bits for the frame.

        This includes the SOF and SFD at the start and the IDL phase at end of frame.
        '''
        for b in [0x55] * 7 + [0xD5]: # SOF + SFD
            for bit in reversed(split_bits(b, 8)):
                yield bit
        for b in self.bytes:
            for bit in reversed(split_bits(b, 8)):
                yield bit
        # IDL = high for 3 bit times -> 6 half-bit times
        for bit in [ManchesterStates.High] * 6:
            yield bit

        yield ManchesterStates.Idle


    def __eq__(self, other):
        if not isinstance(other, EthernetFrame): return False

        s_vars = copy(vars(self))
        s_vars['_crc'] = self.crc
        s_vars['_length_type'] = self.length_type

        o_vars = copy(vars(other))
        o_vars['_crc'] = other.crc
        o_vars['_length_type'] = other.length_type

        #print('## s_vars:')
        #for k in sorted(s_vars.iterkeys()):
        #    print('  {}: {}'.format(k, s_vars[k]))
        #print('## o_vars:')
        #for k in sorted(o_vars.iterkeys()):
        #    print('  {}: {}'.format(k, o_vars[k]))

        return s_vars == o_vars


    def __ne__(self, other):
        return not (self == other)


class EthernetLinkCode(object):
    '''Representation of the pulses in a 100Mbps Ethernet autonegotiation'''
    def __init__(self, selector, tech_ability, rem_fault, ack, next_page):
        '''
        selector (int)
            Identify which standard is in use

        tech_ability (int)
            Technology ability. Identifies posible modes of operation.

        rem_fault (int or bool)
            Flag indicating a link failure

        ack (int or bool)
            Flag to indicate reception of the base link code word.

        next_page (int or bool)
            Flag to indicate intention to send other link code words.
        '''
        self.selector = selector & 0x1F
        self.tech_ability = tech_ability & 0xFF

        self.rem_fault = 1 if rem_fault else 0
        self.ack = 1 if ack else 0
        self.next_page = 1 if next_page else 0

    @property
    def word(self):
        '''Generate 16-bit word from the fields'''
        code = self.selector
        code = (code << 8) + self.tech_ability
        code = (code << 1) + self.rem_fault
        code = (code << 1) + self.ack
        code = (code << 1) + self.next_page

        return code
        


class EthernetLinkTest(object):
    '''An link test pulse or auto-negotiation pulse stream'''
    def __init__(self, link_code=None):
        '''
        link_code (int or None)
            When None, this object represents a single link test pulse.
            When an int, this object represents a series of pulses for the link code
        '''
        self.link_code = link_code

    def edges(self, bit_period):
        '''Get the edges for this object

        bit_period (float)
            The period of a single bit.

        Returns a list of (float, int) edges representing the pulse(s) for this object
        '''
        if self.link_code is None:
            return [(0.0, 1), (bit_period, ManchesterStates.Idle), (2*bit_period, ManchesterStates.Idle)]

        else:
            #print('## code word:', '{:016b}'.format(self.link_code.word))
            code_bits = reversed(split_bits(self.link_code.word, 16))

            edges = []
            t = 0.0
            for b in code_bits:
                edges.extend([(t, 1), (t + bit_period, ManchesterStates.Idle)])
                if b == 1:
                    t += 62.5e-6
                    edges.extend([(t, 1), (t + bit_period, ManchesterStates.Idle)])
                    t += 62.5e-6
                else: # 0
                    t += 125.0e-6

            # Last framing pulse
            edges.extend([(t, 1), (t + bit_period, ManchesterStates.Idle), (t + 2*bit_period, ManchesterStates.Idle)])


            return edges


class EthernetStreamStatus(Enum):
    '''Enumeration for EthernetStreamFrame status codes'''
    CRCError         = stream.StreamStatus.Error + 1


class EthernetStreamFrame(stream.StreamSegment):
    '''Encapsulates an EthernetFrame object into a StreamSegment'''
    def __init__(self, bounds, frame, status=stream.StreamStatus.Ok):
        stream.StreamSegment.__init__(self, bounds, data=frame, status=status)
        self.kind = 'Ethernet frame'

        self.annotate('frame', {}, stream.AnnotationFormat.Hidden)



def ethernet_decode(rxtx, tag_ethertypes=None, logic_levels=None, stream_type=stream.StreamType.Samples):
    '''Decode an ethernet data stream

    This is a generator function that can be used in a pipeline of waveform
    procesing operations.

    Sample streams are a sequence of SampleChunk Objects. Edge streams are a sequence
    of 2-tuples of (time, int) pairs. The type of stream is identified by the stream_type
    parameter. Sample streams will be analyzed to find edge transitions representing
    0 and 1 logic states of the waveforms. With sample streams, an initial block of data
    is consumed to determine the most likely logic levels in the signal.

    rxtx (iterable of SampleChunk objects or (float, int) pairs)
        A sample stream or edge stream representing a differential ethernet signal.

    tag_ethertypes (sequence of int or None)
        The ethertypes to use for identifying 802.1Q tags. Default is 0x8100, 0x88a8, and 0x9100.

    logic_levels ((float, float) or None)
        Optional pair that indicates (low, high) logic levels of the sample
        stream. When present, auto level detection is disabled. This has no effect on
        edge streams.
    
    stream_type (streaming.StreamType)
        A StreamType value indicating that the can parameter represents either Samples
        or Edges

    Yields a series of EthernetStreamFrame objects. Each frame contains subrecords marking the location
      of sub-elements within the frame. CRC errors are recorded as an error status in their
      respective subrecords.
      
    Raises AutoLevelError if stream_type = Samples and the logic levels cannot
      be determined.
    Raises StreamError if ethernet speed cannot be determined.
    '''

    if stream_type == stream.StreamType.Samples:
        if logic_levels is None:
            s_rxtx_it, logic_levels = decode.check_logic_levels(rxtx)
        else:
            s_rxtx_it = rxtx

        hyst_thresholds = decode.gen_hyst_thresholds(logic_levels, expand=3, hysteresis=0.05)
        rxtx_it = decode.find_multi_edges(s_rxtx_it, hyst_thresholds)

        #print('## logic levels:', logic_levels, hyst_thresholds)

    else: # The streams are already lists of edges
        rxtx_it = rxtx

    # Detect speed of ethernet
    buf_edges = 150
    min_edges = 100
    # tee off an iterator to determine speed class
    rxtx_it, speed_check_it = itertools.tee(rxtx_it)

    # Remove Diff-0's #FIX: need to modify to work with 100Mb and 1Gb Enet
    speed_check_it = (edge for edge in speed_check_it if edge[1] != 0)


    symbol_rate_edges = itertools.islice(speed_check_it, buf_edges)
    
    # We need to ensure that we can pull out enough edges from the iterator slice
    # Just consume them all for a count        
    sre_list = list(symbol_rate_edges)
    if len(sre_list) < min_edges:
        raise stream.StreamError('Unable to determine Ethernet speed (not enough edge transitions)')
    del speed_check_it
        
    #print('## sym. rate edges len:', len(sre_list))
    
    raw_symbol_rate = decode.find_symbol_rate(iter(sre_list), spectra=2)
    #print('### raw sym rate:', raw_symbol_rate)

    # For 10baseT (10MHz Manchester) the symbol rate will be 20MHz
    # For 100BaseTX the symbol rate will be 31.25MHz?

    if raw_symbol_rate < 25e6:
        bit_period = 1.0 / 10.0e6
    else:
        raise stream.StreamError('Unsupported Ethernet speed: {}'.format(eng_si(raw_symbol_rate, 'Hz')))


    if stream_type == stream.StreamType.Samples:
        # We needed the bus speed before we could properly strip just
        # the anomalous SE0s
        min_se0 = bit_period * 0.2
        rxtx_it = decode.remove_transitional_states(rxtx_it, min_se0)


    mstates = manchester_decode(rxtx_it, bit_period)

    for r in _ethernet_generic_decode(mstates, tag_ethertypes=tag_ethertypes):
        yield r



def _ethernet_generic_decode(mstates, tag_ethertypes):
    '''Decode Manchester states into ethernet frames'''
    while True:
        try:
            cur_edge = next(mstates)
        except StopIteration:
            break

        if cur_edge[1] == ManchesterStates.High:
            # Possible link test pulse
            ltp_start = cur_edge[0]

            while True:
                try:
                    cur_edge = next(mstates)
                except StopIteration:
                    break

                if cur_edge[1] != ManchesterStates.High:
                    if 90.0e-9 < cur_edge[0] - ltp_start < 110.0e-9: # Pulse should be nominally 100ns wide
                        # Found a LTP
                        ltp = stream.StreamSegment((ltp_start, cur_edge[0]), kind='LTP')
                        ltp.annotate('misc', {})
                        yield ltp
                    break

            continue

        elif cur_edge[1] not in (0, 1):
            continue

        frame_start = cur_edge[0]
        #print('## frame start:', frame_start)

        # Get preamble bits
        get_preamble = True
        prev_bit = cur_edge[1]
        preamble_count = 7*8 + 6 + 1
        # Get alternating 1's and 0's until we see a break in the pattern
        # that indicates we've reached the SFD.
        while preamble_count > 0:
            try:
                cur_edge = next(mstates)
            except StopIteration:
                break

            if cur_edge[1] != 1 - prev_bit:
                break

            prev_bit = cur_edge[1]
            preamble_count -= 1

        # Verify we have the SFD
        if not (prev_bit == 1 and cur_edge[1] == 1):
            # Restart search for a frame
            continue


        # Move to first bit of frame header
        try:
            cur_edge = next(mstates)
        except StopIteration:
            break
        header_start = cur_edge[0]

        frame_bits = []
        bit_start_times = []

        # Get all frame bits
        while cur_edge[1] in (0, 1):
            frame_bits.append(cur_edge[1])
            bit_start_times.append(cur_edge[0])
            try:
                cur_edge = next(mstates)
            except StopIteration:
                break

        crc_end_time = cur_edge[0]

        # Find end of frame
        while True:
            try:
                cur_edge = next(mstates)
            except StopIteration:
                break

            if cur_edge[1] == ManchesterStates.Idle:
                break

        end_time = cur_edge[0]

        #print('## got frame bits:', len(frame_bits))

        # Verify we have a multiple of 8 bits
        if len(frame_bits) % 8 != 0:
            continue

        # Verify we have the minimum of 64 bytes for a frame
        if len(frame_bits) < 64 * 8:
            continue

        # Convert bits to bytes
        frame_bytes = []
        for i in xrange(0, len(frame_bits), 8):
            frame_bytes.append(join_bits(reversed(frame_bits[i:i+8])))

        byte_start_times = [t for t in bit_start_times[::8]]

        #print('## got bytes:', ['{:02x}'.format(b) for b in frame_bytes])

        # Create frame object
        if tag_ethertypes is None:
            tag_ethertypes = [0x8100, 0x88a8, 0x9100]

        tags = []

        lt_start = 12
        length_type = frame_bytes[lt_start] * 256 + frame_bytes[lt_start + 1]
        while length_type in tag_ethertypes: # This is a tag
            tpid = length_type
            tci = frame_bytes[lt_start + 2] * 256 + frame_bytes[lt_start + 3]
            tags.append(EthernetTag(tpid, tci))

            lt_start += 4
            length_type = frame_bytes[lt_start] * 256 + frame_bytes[lt_start + 1]

        if len(tags) == 0: # No tags
            tags = None

        data_bytes = frame_bytes[lt_start+2:-4]
        crc = 0
        for b in frame_bytes[-4:]:
            crc <<= 8
            crc += b
        ef = EthernetFrame(frame_bytes[0:6], frame_bytes[6:12], tags=tags, length_type=length_type, data=data_bytes, crc=crc)

        status = EthernetStreamStatus.CRCError if not ef.crc_is_valid() else stream.StreamStatus.Ok
        sf = EthernetStreamFrame((frame_start, end_time), ef)

        # Annotate fields

        bounds = (byte_start_times[0], byte_start_times[6])
        sf.subrecords.append(stream.StreamSegment(bounds, str(ef.dest), kind='dest'))
        sf.subrecords[-1].annotate('addr', {'_bits':48}, stream.AnnotationFormat.Small)

        bounds = (byte_start_times[6], byte_start_times[12])
        sf.subrecords.append(stream.StreamSegment(bounds, str(ef.source), kind='source'))
        sf.subrecords[-1].annotate('addr', {'_bits':48}, stream.AnnotationFormat.Small)

        # Tags
        if tags is not None:
            for i, t in enumerate(tags):
                bounds = (byte_start_times[12 + 4*i], byte_start_times[12 + 4*i + 4])
                sf.subrecords.append(stream.StreamSegment(bounds, 'tag', kind='tag'))
                sf.subrecords[-1].annotate('ctrl', {}, stream.AnnotationFormat.String)               

        # Ethertype / length
        bounds = (byte_start_times[lt_start], byte_start_times[lt_start+2])
        length_type = ef.length_type

        if length_type >= 0x600:
            kind = 'ethertype'
            if length_type in ethertypes:
                value = ethertypes[length_type]
            else:
                value = 'Unknown: {:04X}'.format(length_type)
            text_format = stream.AnnotationFormat.Small
        else:
            kind = 'length'
            value = length_type
            text_format = stream.AnnotationFormat.Int

        sf.subrecords.append(stream.StreamSegment(bounds, value, kind=kind))
        sf.subrecords[-1].annotate('ctrl', {'_bits':16}, text_format)

        # Data
        bounds = (byte_start_times[lt_start+2], byte_start_times[-4])
        sf.subrecords.append(stream.StreamSegment(bounds, 'Payload, {} bytes'.format(len(data_bytes)), kind='data'))
        sf.subrecords[-1].annotate('data', {}, stream.AnnotationFormat.String)

        # CRC
        bounds = (byte_start_times[-4], crc_end_time)
        status = EthernetStreamStatus.CRCError if not ef.crc_is_valid() else stream.StreamStatus.Ok
        #print('## CRC bytes:', [hex(b) for b in frame_bytes[-4:]])
        sf.subrecords.append(stream.StreamSegment(bounds, frame_bytes[-4:], kind='CRC', status=status))
        sf.subrecords[-1].annotate('check', {}, stream.AnnotationFormat.Hex)

        yield sf


        
def add_overshoot(bits, duration, overshoot=0.75, undershoot=0.8):
    '''Add simulated overshoot to an edge stream

    This function is intended to simulate the overshoot behavior produced by the
    output drivers and magnetics of 10Base-T ethernet. This is done crudely by scaling
    the edge stream values by the overshoot and undershoot factors. This results in a
    non-standard edge stream that can be processed by synth_wave() to create a
    realistic sampled waveform but is otherwise not useful.

    bits (iterable of (float, int))
        A differential edge stream to add overshoot to.

    duration (float)
        The amount of time to add overshoot after each edge transition.

    overshoot (float)
        The fraction of a high-level that the overshoot extends past.

    undershoot (float)
        The fraction of the overshoot that the undershoot extends past. Only used for
        transitions to idle.

    Yields an edge stream with overshoot transitions inserted.
    '''

    undershoot = undershoot * overshoot
    overshoot = 1 + overshoot
    prev_bit = None
    prev_fall = False
    for b in bits:
        if prev_bit is not None:
            if b[0] - prev_bit[0] > duration:
                if prev_bit[1] != 0:
                    yield (prev_bit[0], prev_bit[1] * overshoot)
                    yield (prev_bit[0] + duration, prev_bit[1])

                else: # 0, generate undershoot before idle state
                    if prev_fall:
                        yield (prev_bit[0], -undershoot)
                        yield (prev_bit[0] + duration, prev_bit[1])
                    else:
                        yield prev_bit

            else: # Bit time is shorter than overshoot duration
                yield (prev_bit[0], prev_bit[1] * overshoot)

            prev_fall = True if b[1] < prev_bit[1] else False

        prev_bit = b

    yield prev_bit



def ethernet_synth(frames, overshoot=None, idle_start=0.0, frame_interval=0.0, idle_end=0.0):
    '''Generate synthesized Ethernet frames
    
    frames (sequence of EthernetFrame)
        Frames to be synthesized.

    overshoot (None or (float, float))
        When a pair of floats is provided these indicate the overshoot parameters to add
        to the waveform. The first number is the fraction of a bit period that the overshoot
        covers. This should be less than 0.5. The second number is the fraction of a high-level
        that the overshoot extends past. When used, the edge stream must be converted to a
        sample stream with low-pass filtering by synth_wave() before it accurately represents
        overshoot.

    idle_start (float)
        The amount of idle time before the transmission of frames begins.

    frame_interval (float)
        The amount of time between frames.

    idle_end (float)
        The amount of idle time after the last frame.

    Yields an edge stream of (float, int) pairs. The first element in the iterator
      is the initial state of the stream.
    '''
    bit_period = 1.0 / 10.0e6 #FIX set speed

    frame_its = []
    for i, frame in enumerate(frames):
        istart = idle_start if i == 0 else 0.0
        iend = idle_end if i == len(frames)-1 else bit_period

        if hasattr(frame, 'edges'): # Link pulse
            edges = iter(frame.edges(bit_period))
        else: # A proper frame
            edges = manchester_encode(frame.bit_stream(), bit_period, idle_start=istart, idle_end=iend)

        if overshoot is not None and len(overshoot) == 2:
            frame_its.append(add_overshoot(diff_encode(edges), bit_period * overshoot[1], overshoot[0]))
        else:
            frame_its.append(diff_encode(edges))

    return sigp.chain_edges(frame_interval, *frame_its)



def _crc32_table_gen():
    poly = 0xedb88320
    mask = 0xffffffff

    tbl = [0] * 256

    for i in xrange(len(tbl)):
        sreg = i
        for j in xrange(8):
            if sreg & 0x01 != 0:
                sreg = poly ^ (sreg >> 1)
            else:
                sreg >>= 1;

        tbl[i] = sreg & mask

    return tbl


_crc32_table = _crc32_table_gen()


def table_ethernet_crc32(d):
    '''Calculate Ethernet CRC-32 on data
    
    This is a table-based byte-wise implementation
    
    d (sequence of int)
        Array of integers representing bytes
        
    Returns an integer with the CRC value.
    '''

    sreg = 0xffffffff
    mask = 0xffffffff

    tbl = _crc32_table

    for byte in d:
        tidx = (sreg ^ byte) & 0xff
        sreg = (sreg >> 8) ^ tbl[tidx] & mask

    return sreg ^ mask


