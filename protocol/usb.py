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
    TokenOut   = 0b0001
    TokenIn    = 0b1001
    TokenSOF   = 0b0101
    TokenSetup = 0b1101
    
    Data0 = 0b0011
    Data1 = 0b1011
    Data2 = 0b0111
    MData = 0b1111
    
    ACK   = 0b0010
    NAK   = 0b1010
    STALL = 0b1110
    NYET  = 0b0110
    
    Preamble = 0b1100
    ERR      = 0b1100 # FIX
    Split    = 0b1000
    Ping     = 0b0100

class USBState(object):
    SE0 = 0
    J = 1
    K = 2

class USBPacket(object):
    def __init__(self, pid, speed=USBSpeed.FullSpeed, delay=0.0 ):
        self.speed = speed
        self.pid = pid & 0x0f
        self.delay = delay
        
    def GetStates(self):
        pass
        
        
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
        
        for s in self.GetStates():
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
            
        
    
        
class USBTokenPacket(USBPacket):
    def __init__(self, pid, addr, endp, speed=USBSpeed.FullSpeed, delay=0.0):
        USBPacket.__init__(self, pid, speed, delay)
        self.addr = addr
        self.endp = endp
        
    def GetStates(self):
        # Token packet format:
        #  sync, PID, Addr, Endp, CRC5, EOP
        period = USBClockPeriod[self.speed]
        t = 0.0
        
        J = USBState.J
        K = USBState.K
        
        # initial state J
        states = [(t, J)]
        t += period
        
        # generate sync
        for i in xrange(3):
            states.append((t, K))
            t += period
            states.append((t, J))
            t += period
            
        states.append((t, K))
        t += 2 * period
        
        # generate PID
        prev_state = K
        pid_enc = self.pid << 4 | (~self.pid & 0x0f)
        bits = [int(c) for c in bin(pid_enc & 0xFF)[2:].zfill(8)]
        for b in bits[::-1]:
            # FIX: add bit stuffing
            if b == 0: # toggle
                ns = J if prev_state == K else J
            else: # b == 1, keep state
                ns = prev_state
                
            states.append((t, ns))
            t += period
            
        # generate address
        
        # generate Endp
        
        # generate CRC5
        
        # generate EOP
        states.append((t, 0)) # SE0 for two cycles
        t += 2 * period
        
        states.append((t, J))
        #t += period
        
        return states

                
        
        
class USBDataPacket(USBPacket):
    def __init__(self, pid, data, speed=USBSpeed.FullSpeed, delay=0.0):
        USBPacket.__init__(self, pid, speed, delay)
        self.data = data

class USBHandshakePacket(USBPacket):
    def __init__(self, pid, speed=USBSpeed.FullSpeed, delay=0.0):
        USBPacket.__init__(self, pid, speed, delay)
        
    def GetStates(self):
        # Handshake packet format:
        #  sync, PID, EOP
        period = USBClockPeriod[self.speed]
        t = 0.0
        
        J = USBState.J
        K = USBState.K
        
        # initial state J
        states = [(t, J)]
        t += period
        
        # generate sync
        for i in xrange(3):
            states.append((t, K))
            t += period
            states.append((t, J))
            t += period
            
        states.append((t, K))
        t += 2 * period
        
        # generate PID
        prev_state = K
        pid_enc = self.pid << 4 | (~self.pid & 0x0f)
        bits = [int(c) for c in bin(pid_enc & 0xFF)[2:].zfill(8)]
        for b in bits[::-1]:
            if b == 0: # toggle
                ns = J if prev_state == K else J
            else: # b == 1, keep state
                ns = prev_state
                
            states.append((t, ns))
            t += period
        
        # generate EOP
        states.append((t, 0)) # SE0 for two cycles
        t += 2 * period
        
        states.append((t, J))
        #t += period
        
        return states        
        

class USBSOFPacket(USBPacket):
    def __init__(self, pid, frame_num, speed=USBSpeed.FullSpeed, delay=0.0):
        USBPacket.__init__(self, pid, speed, delay)
        self.frame_num = frame_num
        
        
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
    

def _crc_bits(crc, crc_len):
    ''' Convert integer to an array of bits '''
    bits = [0] * crc_len
    for i in xrange(crc_len-1, -1, -1):
        bits[i] = crc & 0x01
        crc >>= 1
        
    return bits
    
            
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
    
    return _crc_bits(crc, 5)

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
    return _crc_bits(crc, 16)

    
    
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
    
    crc = sreg ^ mask
    return _crc_bits(crc, 16)


# def gen_table():
    # """
    # This function generates the CRC table used for the table_driven CRC
    # algorithm.  The Python version cannot handle tables of an index width
    # other than 8.  See the generated C code for tables with different sizes
    # instead.
    # """
    
    # CrcShift = 0
    # # DirectInit = 0xffff
    # ReflectIn = True
    # MSB_Mask = 0x8000
    # Poly = 0x8005
    # Mask = 0xffff
    # # ReflectOut = False
    # Width = 16
    # # XorOut = 0xffff
    # TableIdxWidth = 8
    
    # DB = 2
    
    # table_length = 1 << TableIdxWidth
    # #print('### tbl len', table_length)
    # tbl = [0] * table_length
    # for i in range(table_length):
        # register = i
        # if ReflectIn:
            # register = reflect(register, TableIdxWidth)

        # register = register << (Width - TableIdxWidth + CrcShift)
        # if i == DB:
            # print('## reflect init', hex(register))
        # for j in range(TableIdxWidth):
            # if register & (MSB_Mask << CrcShift) != 0:
                # register = (register << 1) ^ (Poly << CrcShift)
            # else:
                # register = (register << 1)
            # if i == DB: print('## sr:', hex(register))
                
        # if i == DB:
            # print('##', hex(register))
        # if ReflectIn:
            # register = reflect(register >> CrcShift, Width) << CrcShift
            
        # if i == DB:
            # print('## tbl[{}]:'.format(DB), register & (Mask << CrcShift), hex(register))
        # tbl[i] = register & (Mask << CrcShift)
    # return tbl
    
# def table_driven(in_str):
    # """
    # The Standard table_driven CRC algorithm.
    # """
    
    # CrcShift = 0
    # DirectInit = 0xffff
    # ReflectIn = True
    # MSB_Mask = 0x8000
    # Poly = 0x8005
    # Mask = 0xffff
    # ReflectOut = False
    # Width = 16
    # XorOut = 0xffff
    # TableIdxWidth = 8
    
    
    # tbl = gen_table()
    # print(tbl[:10])

    # register = DirectInit << CrcShift
    # if not ReflectIn:
        # for c in in_str:
            # tblidx = ((register >> (Width - TableIdxWidth + CrcShift)) ^ ord(c)) & 0xff
            # register = ((register << (TableIdxWidth - CrcShift)) ^ tbl[tblidx]) & (Mask << CrcShift)
        # register = register >> CrcShift
    # else:
        # register = reflect(register, Width + CrcShift) << CrcShift
        # for c in in_str:
            # tblidx = ((register >> CrcShift) ^ ord(c)) & 0xff
            # register = ((register >> TableIdxWidth) ^ tbl[tblidx]) & (Mask << CrcShift)
        # register = reflect(register, Width + CrcShift) & Mask

    # if ReflectOut:
        # register = reflect(register, Width)
    # return register ^ XorOut
    
    