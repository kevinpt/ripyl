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
    
    