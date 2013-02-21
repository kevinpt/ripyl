#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Protocol decode library
   USB protocol decoder
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

from decode import *
from streaming import *

class USBFrame(StreamSegment):
    def __init__(self, bounds, data=None):
        StreamSegment.__init__(self, bounds, data)
        self.kind = 'USB frame'
        
    def __str__(self):
        return chr(self.data)


class USBSpeed(object):
    LowSpeed = 0
    FullSpeed = 1
    HighSpeed = 2

USBClockPeriod = {
    USBSpeed.LowSpeed: 1.0 / 1.5e6,
    USBSpeed.FullSpeed: 1.0 / 12.0e6,
    USBSpeed.HighSpeed: 1.0 / 480.0e6
}
    
class USBPID(object):
    # Token PIDs
    TokenOut   = 0b0001
    TokenIn    = 0b1001
    SOF        = 0b0101  # SOF PID
    TokenSetup = 0b1101
    
    # Data PIDs
    Data0 = 0b0011
    Data1 = 0b1011
    Data2 = 0b0111
    MData = 0b1111
    
    # Handshake PIDs
    ACK   = 0b0010
    NAK   = 0b1010
    STALL = 0b1110
    NYET  = 0b0110
    
    
    # Special PIDs
    Preamble = 0b1100
    ERR      = 0b1100 # Reused PREamble PID
    Split    = 0b1000
    Ping     = 0b0100
    EXT      = 0b0000 # Link Power Management extension

class USBState(object):
    SE0 = 0
    J = 1
    K = 2

class USBPacket(object):
    def __init__(self, pid, speed=USBSpeed.FullSpeed, delay=0.0 ):
        self.speed = speed
        self.pid = pid & 0x0f
        self.delay = delay
        self.hs_eop_bits = 8 # High-speed EOP is normally 8-bits. SOF Packet overrides this to 40
        self.hs_sync_dropped_bits = 0 # USB 2.0 7.1.10: Up to 20 bits may be dropped from High-speed sync
        
    def GetBits(self):
        pass
        
    def InitBits(self):
        # sync and PID generation
        bits = []
        
        # generate sync
        if self.speed == USBSpeed.LowSpeed or self.speed == USBSpeed.FullSpeed:
            bits += [0,0,0,0,0,0,0,1]
        else: # High-speed: 15 KJ pairs followed by 2 K's
            drop_bits = self.hs_sync_dropped_bits
            if drop_bits > 20:
                drop_bits = 20
                
            bits += [0] * (30 - drop_bits) + [0, 1]
        
        # generate PID
        pid_rev = int('{:04b}'.format(self.pid)[::-1], base=2) # reverse the bits
        pid_enc = pid_rev << 4 | (pid_rev ^ 0x0f)
        bits += _split_bits(pid_enc, 8)
        
        return bits

    def BitStuff(self, bits):
        sbits = []
        ones = 0
        for b in bits:
            sbits.append(b)
            
            if b == 1:
                ones += 1
            else:
                ones = 0
                
            if ones == 6:
                # stuff a 0 in the bit stream
                sbits.append(0)
                ones = 0
        return sbits
        
    def GetNRZI(self):
        ''' Apply bit stuffing and convert bits to J/K states '''
        period = USBClockPeriod[self.speed]
        t = 0.0

        J = USBState.J
        K = USBState.K
        
        # initial state J
        states = [(t, J)]
        t += period * 3
        
        # bit stuff
        stuffed_bits = self.BitStuff(self.GetBits())
        #stuffed_bits = self.GetBits()

        # High-speed EOP
        if self.speed == USBSpeed.HighSpeed:
            # EOP is signalled with intentional bit-stuff error(s)
            stuffed_bits += [0] + [1] * (self.hs_eop_bits-1)
            print('## EOP bits:', self.hs_eop_bits, bin(self.pid))
            
        
        # convert bits to NRZI J/K states
        prev_state = J
        for b in stuffed_bits:
            if b == 0: # toggle
                ns = J if prev_state == K else K
            else: # b == 1, keep state
                ns = prev_state
                
            prev_state = ns
                
            states.append((t, ns))
            t += period
        
        # generate EOP
        if self.speed == USBSpeed.LowSpeed or self.speed == USBSpeed.FullSpeed:
            states.append((t, 0)) # SE0 for two cycles
            t += 2 * period
        
            states.append((t, J))


        return states
        
        
    def GetEdges(self, cur_time = 0.0):
        if self.speed == USBSpeed.LowSpeed:
            J_DP = 0
            J_DM = 1
            
            K_DP = 1
            K_DM = 0
        else:
            J_DP = 1
            J_DM = 0
            
            K_DP = 0
            K_DM = 1
            
        edges_dp = []
        edges_dm = []
        
        for s in self.GetNRZI():
            t = s[0] + self.delay + cur_time
            if s[1] == USBState.J:
                dp = J_DP
                dm = J_DM
            elif s[1] == USBState.K:
                dp = K_DP
                dm = K_DM
            else: # SE0
                dp = 0
                dm = 0
                
            edges_dp.append((t, dp))
            edges_dm.append((t, dm))
            
        return (edges_dp, edges_dm)
            

def _split_bits(n, num_bits):
    ''' Convert integer to an array of bits '''
    bits = [0] * num_bits
    for i in xrange(num_bits-1, -1, -1):
        bits[i] = n & 0x01
        n >>= 1
        
    return bits
    
        
class USBTokenPacket(USBPacket):
    def __init__(self, pid, addr, endp, speed=USBSpeed.FullSpeed, delay=0.0):
        USBPacket.__init__(self, pid, speed, delay)
        self.addr = addr
        self.endp = endp
        
    def GetBits(self):
        # Token packet format:
        #  sync, PID, Addr, Endp, CRC5
        
        bits = self.InitBits() # sync and PID
            
        # generate address
        check_bits = []
        a = self.addr
        for _ in xrange(7):
            check_bits.append(a & 0x01)
            a >>= 1
        
        # generate Endp
        e = self.endp
        for _ in xrange(4):
            check_bits.append(e & 0x01)
            e >>= 1
        
        # generate CRC5
        crc_bits = usb_crc5(check_bits)
        
        bits += check_bits + crc_bits
        
        return bits

                
        
        
class USBDataPacket(USBPacket):
    def __init__(self, pid, data, speed=USBSpeed.FullSpeed, delay=0.0):
        USBPacket.__init__(self, pid, speed, delay)
        self.data = data
    
    def GetBits(self):
        # Data packet format:
        #  sync, PID, Data, CRC16
        
        bits = self.InitBits() # sync and PID
        
        # calculate CRC16
        crc_bits = table_usb_crc16(self.data)
        
        # add data bits LSB first
        for byte in self.data:
            for _ in xrange(8):
                bits.append(byte & 0x01)
                byte >>= 1
                
        # add CRC
        bits += crc_bits
        
        return bits

class USBHandshakePacket(USBPacket):
    def __init__(self, pid, speed=USBSpeed.FullSpeed, delay=0.0):
        USBPacket.__init__(self, pid, speed, delay)

    def GetBits(self):
        # Handshake packet format:
        #  sync, PID
        
        bits = self.InitBits() # sync and PID
        
        return bits
        

class USBSOFPacket(USBPacket):
    def __init__(self, pid, frame_num, speed=USBSpeed.FullSpeed, delay=0.0):
        USBPacket.__init__(self, pid, speed, delay)
        self.frame_num = frame_num
        self.hs_eop_bits = 40

    def GetBits(self):
        # SOF packet format:
        #  sync, PID, Frame, CRC5
        
        bits = self.InitBits() # sync and PID
        
        # generate frame
        check_bits = []
        f = self.frame_num
        for _ in xrange(11):
            check_bits.append(f & 0x01)
            f >>= 1
        
        # generate CRC5
        crc_bits = usb_crc5(check_bits)
        
        bits += check_bits + crc_bits
        
        return bits


        
def usb_decode(dp, dm, stream_type=StreamType.Samples):
    
    if stream_type == StreamType.Samples:
        # tee off an iterator to determine logic thresholds
        s_dp_it, thresh_it = itertools.tee(dp)
        
        logic = find_logic_levels(thresh_it, max_samples=5000, buf_size=2000)
        if logic is None:
            raise StreamError('Unable to find avg. logic levels of waveform')
        del thresh_it
        
        hyst = 0.4
        dp_it = find_edges(s_dp_it, logic, hysteresis=hyst)
        dm_it = find_edges(dm, logic, hysteresis=hyst)

    else: # the streams are already lists of edges
        dp_it = dp
        dm_it = dm
        
        
        
    # tee off an iterator to determine speed class
    dp_it, speed_check_it = itertools.tee(dp_it)
    buf_edges = 50
    min_edges = 8
    symbol_rate_edges = itertools.islice(speed_check_it, buf_edges)
    
    # We need to ensure that we can pull out enough edges from the iterator slice
    # Just consume them all for a count        
    sre_list = list(symbol_rate_edges)
    if len(sre_list) < min_edges:
        raise StreamError('Unable to determine bus speed (not enough edge transitions)')
        
    print('## sre len:', len(sre_list))
    
    raw_symbol_rate = find_symbol_rate(iter(sre_list), spectra=2)
    # delete the tee'd iterators so that the internal buffer will not grow
    # as the edges_it is advanced later on
    del symbol_rate_edges
    del speed_check_it   
    
    std_bus_speeds = ((USBSpeed.LowSpeed, 1.5e6), (USBSpeed.FullSpeed, 12.0e6), \
        (USBSpeed.HighSpeed, 480.0e6))
    # find the bus speed closest to the raw rate
    bus_speed = min(std_bus_speeds, key=lambda x: abs(x[1] - raw_symbol_rate))[0]
    

    print('### rsr:', USBClockPeriod[bus_speed], raw_symbol_rate)
    
    # # Establish J/K state values
    # if bus_speed == USBSpeed.LowSpeed:
        # J_DP = 0
        # J_DM = 1
    # else:
        # J_DP = 1
        # J_DM = 0
        
    # K_DP = 1 - J_DP
    # K_DM = 1 - J_DM

    
    SE0 = 0
    J = 1
    K = 2
    SE1 = 3 # error condition

    edge_sets = {
        'dp': dp_it,
        'dm': dm_it
    }
    
    es = MultiEdgeSequence(edge_sets, 0.0)
    
    state_seq = EdgeSequence(_convert_single_ended_states(es, bus_speed), 0.0)
    
    # print('##### cs', state_seq.cur_state(), state_seq.cur_time)
    # while not state_seq.at_end():
        # ts = state_seq.advance_to_edge()
        # print('##### cs', state_seq.cur_state(), state_seq.cur_time)
        
    records = _decode_usb_state(state_seq, bus_speed)
    
    return records

def _decode_usb_state(state_seq, bus_speed):
    while not state_seq.at_end():
        ts = state_seq.advance_to_edge()


def _convert_single_ended_states(es, bus_speed):
    SE0 = 0 #FIX move these
    J = 1
    K = 2
    SE1 = 3 # error condition

    # Establish J/K state values
    if bus_speed == USBSpeed.LowSpeed:
        J_DP = 0
        J_DM = 1
    else:
        J_DP = 1
        J_DM = 0
        
    K_DP = 1 - J_DP
    K_DM = 1 - J_DM
    
    def decode_state(cur_dp, cur_dm):
        cur_bus = SE1
        if cur_dp == 0    and cur_dm == 0:    cur_bus = SE0
        if cur_dp == J_DP and cur_dm == J_DM: cur_bus = J
        if cur_dp == K_DP and cur_dm == K_DM: cur_bus = K
            
        return cur_bus
            
    cur_bus = decode_state(es.cur_state('dp'), es.cur_state('dm'))
    yield (es.cur_time(), cur_bus)
    
    while not es.at_end():
        prev_bus = cur_bus
        ts, cname = es.advance_to_edge()
        
        # Due to channel skew we can get erroneous SE0 and SE1 decodes
        # on the bus so skip ahead by a small amount to ensure that any
        # near simultaneous transition has happened.
        
        skew_adjust = 1.0e-9 # FIX: adjust for bus speed
        es.advance(skew_adjust)
        
        cur_bus = decode_state(es.cur_state('dp'), es.cur_state('dm'))
        #print('## pb, cb:', prev_bus, cur_bus, ts, es.cur_time() - skew_adjust)
        yield (es.cur_time() - skew_adjust, cur_bus)
        

    

        
def usb_synth(packets, idle_start=0.0, idle_end=0.0):
    t = 0.0
    dp = 0
    dm = 0
    
    yield ((t, dp), (t, dm)) # initial conditions
    t += idle_start

    for p in packets:
        edges_dp , edges_dm = p.GetEdges(t)
        
        for dp, dm in zip(edges_dp, edges_dm):
            yield (dp, dm)
        
        # update time to end of edge sequence plus a clock period
        t = edges_dp[-1][0] + USBClockPeriod[p.speed]
 
    dp = 0
    dm = 0
    yield ((t, dp), (t, dm))
    t += idle_end
    yield ((t, dp), (t, dm)) # final state
    
    
            
def usb_crc5(d):
    ''' Calculate USB CRC-5 on data
    d
        Array of integers representing 0 or 1 bits
        
    Returns array of integers for each bit in the CRC with LSB first
    '''
    poly = 0x5   # USB CRC-5 polynomial
    sreg = 0x1f  # prime register with 1's
    mask = 0x1f
    
    for b in d:
        leftbit = (sreg & 0x10) >> 4
        sreg = (sreg << 1) & mask
        if b != leftbit:
            sreg ^= poly

    crc = sreg ^ mask  # invert shift register contents
    
    return _split_bits(crc, 5)

def usb_crc16(d):
    ''' Calculate USB CRC-16 on data
    d
        Array of integers representing 0 or 1 bits
        
    Returns array of integers for each bit in the CRC with LSB first
    '''
    poly = 0x8005  # USB CRC-16 polynomial
    sreg = 0xffff  # prime register with 1's
    mask = 0xffff
    
    for b in d:
        leftbit = (sreg & 0x8000) >> 15
        #print('## lb:', leftbit)
        sreg = (sreg << 1) & mask
        if b != leftbit:
            sreg ^= poly

    crc = sreg ^ mask  # invert shift register contents
    return _split_bits(crc, 16)

    
    
def _crc16_table_gen():
    poly = 0x8005 # USB CRC-16 polynomial
    mask = 0xffff

    tbl = [0] * 256
        
    for i in xrange(len(tbl)):
        sreg = i
        sreg = int('{:08b}'.format(sreg)[::-1], base=2) # reverse the bits

        sreg <<= 8
        for j in xrange(8):
            if sreg & 0x8000 != 0:
                sreg = (sreg << 1) ^ poly
            else:
                sreg = sreg << 1
                
        sreg = sreg & mask # remove shifted out bits
        sreg = int('{:016b}'.format(sreg)[::-1], base=2) # reverse the bits
        tbl[i] = sreg & mask
        
    return tbl
    
_crc16_table = _crc16_table_gen()

def table_usb_crc16(d):
    ''' Calculate USB CRC-16 on data
    
    This is a table-based byte-wise implementation
    
    d
        Array of integers representing bytes
        
    Returns array of integers for each bit in the CRC with LSB first
    '''
    
    sreg = 0xffff # prime register with 1's
    mask = 0xffff
    
    tbl = _crc16_table

    for byte in d:
        tidx = (sreg ^ byte) & 0xff
        sreg = ((sreg >> 8) ^ tbl[tidx]) & mask

    sreg = int('{:016b}'.format(sreg)[::-1], base=2) # reverse the bits
    
    crc = sreg ^ mask # invert shift register contents
    return _split_bits(crc, 16)
