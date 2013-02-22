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
    TokenOut   = 0b0001  # USBTokenPacket()
    TokenIn    = 0b1001  # USBTokenPacket()
    SOF        = 0b0101  # USBSOFPacket()
    TokenSetup = 0b1101  # USBTokenPacket()
    
    # Data PIDs
    Data0 = 0b0011  # USBDataPacket() ...
    Data1 = 0b1011
    Data2 = 0b0111
    MData = 0b1111
    
    # Handshake PIDs
    ACK   = 0b0010  # USBHandshakePacket() ...
    NAK   = 0b1010
    STALL = 0b1110
    NYET  = 0b0110
    
    
    # Special PIDs
    PRE   = 0b1100 # USBHandshakePacket()  (Low and Full speed only)
    ERR   = 0b1100 # USBHandshakePacket()  (Reused PREamble PID High speed only)
    SPLIT = 0b1000 # USBSplitPacket()
    PING  = 0b0100 # USBTokenPacket()
    EXT   = 0b0000 # USBEXTPacket()  (extended token format from Link Power Management ECN)

class USBPacketKind(object):
    Token = 0b01
    Data = 0b11
    Handshake = 0b10
    Special = 0b00

def _get_packet_kind(pid):
    return pid & 0x03


class USBState(object):
    SE0 = 0
    J = 1
    K = 2
    SE1 = 3 # error condition

    
class USBStreamPacket(StreamSegment):
    def __init__(self, bounds, packet, crc=None, status=StreamStatus.Ok):
        StreamSegment.__init__(self, bounds, data=None, status=status)
        self.kind = 'USB packet'
        
        self.packet = packet # USBPacket object
        self.crc = crc
        
    def __str__(self):
        return chr(self.data)

    
class USBPacket(object):
    '''

    Note: These objects have methods meant to be used by the usb_synth() routine. When
    embedded in a USBStreamPacket object they are used for attribute access only.
    
    '''
    def __init__(self, pid, speed=USBSpeed.FullSpeed, delay=0.0 ):
        self.speed = speed
        self.pid = pid & 0x0f
        self.delay = delay
        self.hs_eop_bits = 8 # High-speed EOP is normally 8-bits. SOF Packet overrides this to 40
        self.hs_sync_dropped_bits = 0 # USB 2.0 7.1.10: Up to 20 bits may be dropped from High-speed sync
        
    def get_bits(self):
        raise NotImplementedError('USBPacket must be sub-classed')
        
    def init_bits(self):
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

    def bit_stuff(self, bits):
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
        
    def get_NRZI(self):
        ''' Apply bit stuffing and convert bits to J/K states '''
        period = USBClockPeriod[self.speed]
        t = 0.0

        J = USBState.J
        K = USBState.K
        SE0 = USBState.SE0
        
        # initial state idle
        if self.speed == USBSpeed.LowSpeed or self.speed == USBSpeed.FullSpeed:
            states = [(t, J)]
        else: # HighSpeed
            states = [(t, SE0)]
            
        t += period * 3 #FIX: arbitrary
        
        # bit stuff
        stuffed_bits = self.bit_stuff(self.get_bits())
        #stuffed_bits = self.get_bits()

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
        else: # HighSpeed
            states.append((t, SE0))
        

        #print('$$$$ NRZI states:', zip(*states)[1])
        return states
        
        
    def get_edges(self, cur_time = 0.0):
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
        
        for s in self.get_NRZI():
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

            # if self.delay > 0.0:
                # print('^^^^^^^^^ ', s[1], self.delay)
                
            edges_dp.append((t, dp))
            edges_dm.append((t, dm))
            
        return (edges_dp, edges_dm)
            

def _split_bits(n, num_bits):
    ''' Convert integer to an array of bits (MSB-first) '''
    bits = [0] * num_bits
    for i in xrange(num_bits-1, -1, -1):
        bits[i] = n & 0x01
        n >>= 1
        
    return bits
    
   
def _join_bits(bits):
    ''' Convert an array of bits (MSB first) to an integer word '''
    word = 0
    for b in bits:
        word = (word << 1) | b
        
    return word
    
        
class USBTokenPacket(USBPacket):
    def __init__(self, pid, addr, endp, speed=USBSpeed.FullSpeed, delay=0.0):
        USBPacket.__init__(self, pid, speed, delay)
        self.addr = addr
        self.endp = endp
        
    def get_bits(self):
        # Token packet format:
        #  sync, PID, Addr, Endp, CRC5
        
        start_bits = self.init_bits() # sync and PID
            
        # generate address
        check_bits = []
        # a = self.addr
        # for _ in xrange(7):
            # check_bits.append(a & 0x01)
            # a >>= 1
        check_bits += reversed(_split_bits(self.addr, 7))
        
        # generate Endp
        # e = self.endp
        # for _ in xrange(4):
            # check_bits.append(e & 0x01)
            # e >>= 1
        check_bits += reversed(_split_bits(self.endp, 4))
        
        # generate CRC5
        crc_bits = usb_crc5(check_bits)
        print('$$$$ Token CRC5', crc_bits)
        
        return start_bits + check_bits + crc_bits
        
    def __repr__(self):
        return 'USBTokenPacket({}, {}, {}, {}, {})'.format(hex(self.pid), hex(self.addr), \
            hex(self.endp), self.speed, self.delay)

                
        
        
class USBDataPacket(USBPacket):
    def __init__(self, pid, data, speed=USBSpeed.FullSpeed, delay=0.0):
        USBPacket.__init__(self, pid, speed, delay)
        self.data = data
    
    def get_bits(self):
        # Data packet format:
        #  sync, PID, Data, CRC16
        
        bits = self.init_bits() # sync and PID
        
        # calculate CRC16
        crc_bits = table_usb_crc16(self.data)
        print('$$$$ Data CRC16', crc_bits)
        
        # add data bits LSB first
        for byte in self.data:
            for _ in xrange(8):
                bits.append(byte & 0x01)
                byte >>= 1
                
        # add CRC
        bits += crc_bits
        
        return bits

    def __repr__(self):
        return 'USBDataPacket({}, {}, {}, {})'.format(hex(self.pid), self.data, \
            self.speed, self.delay)

        
class USBHandshakePacket(USBPacket):
    def __init__(self, pid, speed=USBSpeed.FullSpeed, delay=0.0):
        USBPacket.__init__(self, pid, speed, delay)

    def get_bits(self):
        # Handshake packet format:
        #  sync, PID
        
        bits = self.init_bits() # sync and PID
        
        return bits

    def __repr__(self):
        return 'USBHandshakePacket({}, {}, {})'.format(hex(self.pid), self.speed, self.delay)        

class USBSOFPacket(USBPacket):
    def __init__(self, pid, frame_num, speed=USBSpeed.FullSpeed, delay=0.0):
        USBPacket.__init__(self, pid, speed, delay)
        self.frame_num = frame_num
        self.hs_eop_bits = 40

    def get_bits(self):
        # SOF packet format:
        #  sync, PID, Frame, CRC5
        
        bits = self.init_bits() # sync and PID
        
        # generate frame
        check_bits = []
        f = self.frame_num
        for _ in xrange(11):
            check_bits.append(f & 0x01)
            f >>= 1
        
        # generate CRC5
        crc_bits = usb_crc5(check_bits)
        print('$$$$ SOF CRC5', crc_bits)
        bits += check_bits + crc_bits
        
        return bits

    def __repr__(self):
        return 'USBSOFPacket({}, {}, {}, {})'.format(hex(self.pid), hex(self.frame_num), \
            self.speed, self.delay)

class USBSplitPacket(USBPacket):
    def __init__(self, pid, addr, sc, port, s, e, et, speed=USBSpeed.HighSpeed, delay=0.0):
        USBPacket.__init__(self, pid, speed, delay)
        self.addr = addr
        self.sc = sc
        self.port = port
        self.s = s
        
        self.e = e
        # e field is unused for CSPLIT tokens
        if self.sc == 1:
            self.e = 0
        
        self.et = et
        
    def get_bits(self):
        # Split packet format:
        #  sync, PID, Addr, SC, Port, S, E/U, ET, CRC5
        
        start_bits = self.init_bits() # sync and PID
            
        # generate address
        check_bits = []
        
        check_bits += reversed(_split_bits(self.addr, 7))
        
        # SC field
        check_bits.append(self.sc & 0x01)
        
        # Port field
        check_bits += reversed(_split_bits(self.port, 7))
        
        # S field
        check_bits.append(self.s & 0x01)
        
        # E field
        # unused for CSPLIT tokens
        check_bits.append(self.e & 0x01)
        
        # ET field
        check_bits += reversed(_split_bits(self.et, 2))
        

        # generate CRC5
        crc_bits = usb_crc5(check_bits)
        print('$$$$ Token CRC5', crc_bits)
        
        return start_bits + check_bits + crc_bits
  
    def __repr__(self):
        return 'USBSplitPacket({}, {}, {}, {}, {}, {}, {}, {}, {})'.format(hex(self.pid), hex(self.addr), \
            self.sc, hex(self.port), self.s, self.e, hex(self.et), self.speed, self.delay)
            
            
class USBEXTPacket(USBPacket):
    def __init__(self, pid, addr, endp, sub_pid, variable, speed=USBSpeed.FullSpeed, delay=0.0):
        USBPacket.__init__(self, pid, speed, delay)
        self.addr = addr
        self.endp = endp
        
        self.sub_pid = sub_pid
        self.variable = variable

    # Instead of defining the get_bits() method we "hack" the existing packet objects to
    # synthesize an extended packet from two other packet types.
    # This is necessary since we need to add an interpacket gap between the two parts
    # of the extended token which needs to be done after conversion to NRZI.

    def get_NRZI(self):
        # Make some dummy packet objects
        
        tok_packet = USBTokenPacket(self.pid, self.addr, self.endp, speed=self.speed)
        
        # split the 11-bit variable into 7-bit and 4-bit parts so they
        # can be stuffed into another USBTokenPacket()
        ext_addr = self.variable & 0x7FF
        ext_endp = (self.variable >> 11) & 0x0F
        ext_packet = USBTokenPacket(self.sub_pid, ext_addr, ext_endp, speed=self.speed)
        
        tok_nrzi = tok_packet.get_NRZI()
        ext_nrzi = ext_packet.get_NRZI()
        
        # construct the interpacket gap
        if self.speed == USBSpeed.LowSpeed or self.speed == USBSpeed.FullSpeed:
            idle_state = USBState.J
            gap_bit_times = 4 # Minimum is 2 bit times
        else: # HighSpeed
            idle_state = USBState.SE0
            gap_bit_times = 40 # Minimum is 32 bit times

        ig_start_time = tok_nrzi[-1][0] + USBClockPeriod[self.speed]
        tok_nrzi.append((ig_start_time, idle_state))
        
        # Adjust bit times in ext NRZI list
        ext_start_time = tok_nrzi[-1][0] + gap_bit_times * USBClockPeriod[self.speed]
        for i in xrange(len(ext_nrzi)):
            t, s = ext_nrzi[i]
            ext_nrzi[i] = (t + ext_start_time, s)
            
        tok_nrzi += ext_nrzi
        
        return tok_nrzi
        
    def __repr__(self):
        return 'USBEXTPacket({}, {}, {}, {}, {}, {}, {})'.format(hex(self.pid), hex(self.addr), \
            hex(self.endp), hex(self.sub_pid), hex(self.variable), self.speed, self.delay)
            
        
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
        
    print('## sym. rate edges len:', len(sre_list))
    
    raw_symbol_rate = find_symbol_rate(iter(sre_list), spectra=2, discard_span_limit=5.0e-6)
    # delete the tee'd iterators so that the internal buffer will not grow
    # as the edges_it is advanced later on
    del symbol_rate_edges
    del speed_check_it   
    
    std_bus_speeds = ((USBSpeed.LowSpeed, 1.5e6), (USBSpeed.FullSpeed, 12.0e6), \
        (USBSpeed.HighSpeed, 480.0e6))
    # find the bus speed closest to the raw rate
    bus_speed = min(std_bus_speeds, key=lambda x: abs(x[1] - raw_symbol_rate))[0]
    

    print('### raw symbol rate:', USBClockPeriod[bus_speed], raw_symbol_rate)
    

    edge_sets = {
        'dp': dp_it,
        'dm': dm_it
    }
    
    es = MultiEdgeSequence(edge_sets, 0.0)
    
    state_seq = EdgeSequence(_convert_single_ended_states(es, bus_speed), 0.0)
        
    records = _decode_usb_state(state_seq, bus_speed)
    
    return records

def _decode_usb_state(state_seq, bus_speed):
    SE0 = USBState.SE0
    J = USBState.J
    K = USBState.K
    SE1 = USBState.SE1

    cur_bus = state_seq.cur_state()
    while not state_seq.at_end():
        prev_bus = cur_bus
        ts = state_seq.advance_to_edge()
        cur_bus = state_seq.cur_state()
        packet_start = state_seq.cur_time    
        
        clock_period = USBClockPeriod[bus_speed]

        # look for a start of packet:
        #   Low and Full: Transition from J to K
        #   High: Transition from SE0 to K
        get_packet = False
        if bus_speed == USBSpeed.LowSpeed or bus_speed == USBSpeed.FullSpeed:
            if prev_bus == J and cur_bus == K:
                
                # move to middle of current K state
                state_seq.advance(clock_period / 2.0)
                if state_seq.cur_state() == K: # still valid
                    sync_pattern = [J, K, J, K, J, K, K]
                    get_packet = True
                    for p in sync_pattern:
                        # move to next sync bit
                        state_seq.advance(clock_period)
                        if state_seq.cur_state() != p: # pattern mismatch
                            get_packet = False
                            break
                            
                        #print('#### sync pat:', get_packet)
                            
        else: # HighSpeed SOP
            if prev_bus == SE0 and cur_bus == K:
                # move to middle of current K state
                state_seq.advance(clock_period / 2.0)
                if state_seq.cur_state() == K: # still valid
                    # A chain of High-speed hubs can drop up to 20 sync bits
                    # We're only guaranteed 12. We may be on the first K and the
                    # last one is K so check for 5 JK's first
                    sync_pattern = [J, K] * 5
                    get_packet = True
                    for p in sync_pattern:
                        # move to next sync bit
                        state_seq.advance(clock_period)
                        if state_seq.cur_state() != p: # pattern mismatch
                            get_packet = False
                            break
                            
                    if get_packet: # first part matched, now look for end of sync
                        # now look for alternating JK's or KK for end of sync
                        cur_bus = state_seq.cur_state() # should be K
                        s_count = 0
                        while True:
                            prev_bus = cur_bus
                            state_seq.advance(clock_period)
                            s_count += 1
                            cur_bus = state_seq.cur_state()
                            
                            if not (cur_bus == J or cur_bus == K): # invalid sync state
                                get_packet = False
                                break
                            
                            if prev_bus == K and cur_bus == K: # found sync end
                                break
                                
                            elif (prev_bus == J and cur_bus == J) or s_count > 20: # invalid sync
                                get_packet = False
                                break

        if not get_packet: # we didn't find a valid sync
            cur_bus = state_seq.cur_state()
            continue

            
        # We have potentially found a sync field
        # but this could be packet data that has the same pattern
        # A bad PID, CRC, or premature SE0 will catch this
        
        # Get the remaining states in the packet.
        # We will adjust timings to keep ourselves positioned in the center of a bit
        packet_states = []
        state_seq.advance(clock_period)  # At middle of first PID bit
        time_adjustment = 0.0
        while state_seq.cur_state() != SE0:
            packet_states.append(state_seq.cur_state())
            
            time_step = clock_period
            # only perform adjustment if it's magnitude is more than 1ps
            if abs(time_adjustment) >= 1.0e12:
                time_step += time_adjustment
                
            state_seq.advance(time_step)
            
            # Make timing adjustment if there is a state transition coming up within next bit period
            next_edge_time = state_seq.next_states[0]
            next_step = next_edge_time - state_seq.cur_time
            if next_step < clock_period:
                time_adjustment = next_step - (clock_period / 2.0)
                    
            
        cur_bus = state_seq.cur_state()
        packet_end = state_seq.cur_time
            
        # We need at least 8 states/bits to retrieve the PID
        if len(packet_states) < 8:
            continue

            
        packet_bits = _decode_NRZI(packet_states)
        print('#### Packet states:', packet_states, packet_bits, len(packet_bits))
        
        # Validate the PID
        packet_check = packet_bits[4:8]
        for i, b in enumerate(packet_check): # invert the check bits
            packet_check[i] = 1 - b
            
        if packet_bits[0:4] != packet_check: # invalid PID
            continue
        
        pid = _join_bits(reversed(packet_bits[0:4]))
            
        print('### PID:', bin(pid), packet_bits[0:8])
        
        packet_kind = _get_packet_kind(pid)
        
        # A USB 2.0 hub chain can add up to 20 random bits to the end of a HighSpeed packet.
        # We need to strip the HighSpeed EOP fom the end of the packet_bits before unstuffing
        # so that we can determine the length of a data packet later. If we wait, the unstuffing
        # will mangle the EOP and make things less dependable.
        eop_bits = 0
        if bus_speed == USBSpeed.HighSpeed and packet_kind == USBPacketKind.Data:
            # We need to find the *start* of the EOP
            trailing_data = list(reversed(packet_bits[-28:]))
            # look for reversed EOP pattern in trailing data
            eop_pat = [1,1,1,1,1,1,1,0]
            eop_bits = 0
            for i in xrange(len(trailing_data) - 8):
                sliding_window = trailing_data[i:i+8]
                if sliding_window == eop_pat: # found EOP
                    eop_bits = i + 8
                    
            if eop_bits == 0: # no EOP found
                pass #FIX report packet error
                print('######### ERROR NO EOP found in data packet', trailing_data)
                continue
        
        
        # Unstuff the bits
        # Technically the final 1 in the sync participates in the stuffing
        # but there is guaranteed to be a 0 in the PID field before 6 1's go by
        # so we don't bother including it in packet_bits.
        unstuffed_bits, stuffing_errors = _unstuff(packet_bits[0:len(packet_bits)-eop_bits])
        
        # Low and Full speed packets should have no stuffing errors
        # HighSpeed packets will have stuffing errors from their EOP.
        continue_decode = True
        print('@@@@@@@@@@@@@ STUFFING ERRORS', stuffing_errors, len(packet_bits))
        if len(stuffing_errors) > 0:
            if (bus_speed == USBSpeed.LowSpeed or bus_speed == USBSpeed.FullSpeed):
                continue_decode = False # there was a stuffing error
            else: # HighSpeed
                # For all packets except SOF there should be one stuffing error
                # before the end.
                if pid != USBPID.SOF:
                    if stuffing_errors[0] != len(packet_bits)-1:
                        continue_decode = False # there was a stuffing error not in the EOP
                else: #SOF HighSpeed will have multiple stuffing errors in EOP
                    # The first stuffing error should have been on bit-31
                    if stuffing_errors[0] != 31:
                        continue_decode = False # there was a stuffing error not in the EOP
                
        if continue_decode:
            print('@@@ UNSTUFFED:', unstuffed_bits, len(unstuffed_bits))
            if (packet_kind == USBPacketKind.Token and pid != USBPID.SOF) or pid == USBPID.PING:
                ### Token packet. We should have 8 + 16 bits of data
                #if len(packet_bits) >= (8+16): #FIX: check lengths of packet data
                
                addr_bits = unstuffed_bits[8:8+7]
                addr = _join_bits(reversed(addr_bits))

                endp_bits = unstuffed_bits[8+7:8+11]
                endp = _join_bits(reversed(endp_bits))
                
                crc5_bits = unstuffed_bits[8+11:8+11+5]
                # check the CRC
                crc_check = usb_crc5(addr_bits + endp_bits)
                status = StreamStatus.Error if crc_check != crc5_bits else StreamStatus.Ok
                
                # Construct the stream record
                raw_packet = USBTokenPacket(pid, addr, endp, bus_speed)
                packet = USBStreamPacket((packet_start, packet_end), raw_packet, crc5_bits, status=status)
                yield packet                  

                
            elif pid == USBPID.SOF:
                ### SOF packet. We should have 8 + 16 bits of data
                frame_num_bits = unstuffed_bits[8:8+11]
                frame_num = _join_bits(reversed(frame_num_bits))
                crc5_bits = unstuffed_bits[8+11:8+11+5]
                # check the CRC
                crc_check = usb_crc5(frame_num_bits)
                status = StreamStatus.Error if crc_check != crc5_bits else StreamStatus.Ok
                
                # Construct the stream record
                raw_packet = USBSOFPacket(pid, frame_num, bus_speed)
                packet = USBStreamPacket((packet_start, packet_end), raw_packet, crc5_bits, status=status)
                yield packet               
                
            elif packet_kind == USBPacketKind.Data:
                ### Data packet. Unknown length

                # Determine number of bytes in packet
                data_bits = len(unstuffed_bits) - 8 - 16 # take away PID and CRC bits
                data_bytes = data_bits // 8
                
                # Check for non-multiple of 8
                if data_bytes * 8 != data_bits:
                    pass #FIX report packet error
                    print('######## ERROR bits in data packet not multiple of 8')
                    continue
                    
                data = []
                for i in xrange(data_bytes):
                    byte = _join_bits(reversed(unstuffed_bits[8 + i*8: 8 + i*8 + 8]))
                    data.append(byte)
                
                print('DECODED DATA:', data)
                
                crc16_bits = unstuffed_bits[-16:]
                
                # check the CRC
                crc_check = table_usb_crc16(data)
                status = StreamStatus.Error if crc_check != crc16_bits else StreamStatus.Ok

                # Construct the stream record
                raw_packet = USBDataPacket(pid, data, bus_speed)
                packet = USBStreamPacket((packet_start, packet_end), raw_packet, crc16_bits, status=status)
                yield packet

                
            elif packet_kind == USBPacketKind.Handshake or pid == USBPID.ERR:
                ### Handshake packet. We should have 8-bits of data
                # This also catches PREamble packets which use the same PID as ERR
                # PRE is only used in Low and Full speed USB
                # ERR is only used in High speed USB
                
                # Construct the stream record
                raw_packet = USBHandshakePacket(pid, bus_speed)
                packet = USBStreamPacket((packet_start, packet_end), raw_packet, status=StreamStatus.Ok)
                yield packet

            else: # One of the "special" packets
                if pid == USBPID.SPLIT:
                    ### Split packet. We should have 8 + 24 bits of data
                    #if len(packet_bits) >= (8+16): #FIX: check lengths of packet data
                    
                    addr_bits = unstuffed_bits[8:8+7]
                    addr = _join_bits(reversed(addr_bits))
                    
                    sc = unstuffed_bits[8+7]
                    
                    port_bits = unstuffed_bits[8+8:8+8+7]
                    port = _join_bits(reversed(port_bits))
                    
                    s = unstuffed_bits[8+7+1+7]
                    
                    e = unstuffed_bits[8+7+1+7+1]
                    
                    et_bits = unstuffed_bits[8+17:8+17+2]
                    et = _join_bits(reversed(et_bits))
                    
                    crc5_bits = unstuffed_bits[8+17+2:8+17+2+5]
                    # check the CRC
                    crc_check = usb_crc5(addr_bits + [sc] + port_bits + [s, e] + et_bits)
                    status = StreamStatus.Error if crc_check != crc5_bits else StreamStatus.Ok
                    
                    # Construct the stream record
                    raw_packet = USBSplitPacket(pid, addr, sc, port, s, e, et, bus_speed)
                    packet = USBStreamPacket((packet_start, packet_end), raw_packet, crc5_bits, status=status)
                    yield packet  
                    
                elif pid == USBPID.EXT:
                    ### Extended packet used by Link Power Management
                    pass
                
        else: # handle stuffing error
            pass # FIX

                

        
def _unstuff(packet_bits):
    unstuffed = []
    ones = 0
    expect_stuffing = False
    stuffing_errors = []
    for i, b in enumerate(packet_bits):
        if not expect_stuffing:
            unstuffed.append(b)
        else:
            # should have a stuffed 0
            if b != 0:
                stuffing_errors.append(i)

        expect_stuffing = False

        if b == 1:
            ones += 1
        else:
            ones = 0
            
        if ones == 6:
            # next bit should be a stuffed 0
            expect_stuffing = True
            ones = 0
            
    return (unstuffed, stuffing_errors)

    
def _decode_NRZI(packet_states):
    # previous state was a K from end of sync
    prev_state = USBState.K
    bits = []
    for s in packet_states:
        if s == prev_state: # no toggle -> 1-bit
            bits.append(1)
        else: # toggle -> 0-bit
            bits.append(0)
            
        prev_state = s
            
    return bits


def _convert_single_ended_states(es, bus_speed):

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
        cur_bus = USBState.SE1
        if cur_dp == 0    and cur_dm == 0:    cur_bus = USBState.SE0
        if cur_dp == J_DP and cur_dm == J_DM: cur_bus = USBState.J
        if cur_dp == K_DP and cur_dm == K_DM: cur_bus = USBState.K
            
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
        edges_dp , edges_dm = p.get_edges(t)
        
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
    # Note: crc is in LSB-first order    
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
    # Note: crc is in LSB-first order
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
    
    # Note: crc is in LSB-first order
    return _split_bits(crc, 16)
