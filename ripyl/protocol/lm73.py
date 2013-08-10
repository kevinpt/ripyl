#!/usr/bin/python
# -*- coding: utf-8 -*-

'''LM73 (temperature sensor) protocol decoder
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

import itertools

from ripyl.streaming import *
from ripyl.util.enum import Enum
import ripyl.protocol.i2c as i2c

class LM73Register(Enum):
    '''Enumeration for LM73 registers'''
    Temperature = 0
    Configuration = 1
    THigh = 2
    TLow = 3
    ControlStatus = 4
    Identification = 7
    
LM73ID = 0x190
LM73Addresses = set([0x48, 0x49, 0x4A, 0x4C, 0x4D, 0x4E])

class LM73Operation(Enum):
    '''Enumeration for LM73 bus operations'''
    SetPointer = 0
    WriteData = 1
    ReadData = 2
    
class LM73Transfer(object):
    '''Represent a transaction for the LM73'''
    def __init__(self, address, op, reg=LM73Register.Temperature, data=None):
        '''
        address (int)
            Address of the transfer
            
        op (LM73Operation)
            The operation for this transfer
            
        reg (LM73Register)
            The register used in this transfer
            
        data (sequence of ints)
            List of bytes read/written in the transfer
        '''
        self.address = address
        self.op = op
        self.data = data
        self.reg = reg
        self.i2c_tfer = None
        
    def __repr__(self):
        if self.data is not None:
            h_data = '[{}]'.format(', '.join(hex(d) for d in self.data))
        else:
            h_data = None
            
        return 'LM73Transfer({}, {}, {}, {})'.format(hex(self.address), LM73Operation(self.op), \
            LM73Register(self.reg), h_data)
            
    @property
    def temperature(self):
        '''Compute the temperature in Celcius

        Returns a float
        '''
        if self.reg in (LM73Register.Temperature, LM73Register.THigh, LM73Register.TLow) \
            and self.op == LM73Operation.ReadData:
            return float((self.data[0] << 8) + self.data[1]) * 0.25 / 32.0
        else:
            return None
            
    def __eq__(self, other):
        match = True
        
        if self.address != other.addres: match = False
        if self.op != other.op: match = False
        if self.data != other.data: match = False
        if self.reg != other.reg: match = False
        
        return match
    
    def __ne__(self, other):
        return not self == other       


def lm73_decode(stream, addresses=LM73Addresses):
    '''Decode an LM73 data stream
    
    stream (sequence of StreamRecord or I2CTransfer)
        An iterable representing either a stream of I2C StreamRecord objects or
        I2CTransfer objects produced by i2c_decode() or reconstruct_i2c_transfers() respectively.
    
    addresses (set of ints)
        A collection identifying the valid LM73 addresses to decode. All others are ignored.
        
    Yields a series of LM73Transfer objects.
    '''
    cur_reg = LM73Register.Temperature
    
    # check type of stream
    stream_it, check_it = itertools.tee(stream)
    try:
        rec0 = next(check_it)
    except StopIteration:
        # Stream is empty
        rec0 = None
        
    if rec0 is not None:
        if isinstance(rec0, StreamRecord):
            # Convert the stream to a set of I2C transfers
            stream_it = i2c.reconstruct_i2c_transfers(stream_it)
            
    del check_it
    
    for tfer in stream_it:
        if tfer.address not in addresses:
            continue
        
        if tfer.r_wn == i2c.I2C.Write:
            if len(tfer.data) == 0: # Error condition
                # This should only happen if the data portion of a write is missing
                continue # FIX: do something more useful
            
            elif len(tfer.data) == 1: # Set pointer op
                cur_reg = tfer.data[0]
                lm_tfer = LM73Transfer(tfer.address, LM73Operation.SetPointer, cur_reg, None)

            else: # Write data
                cur_reg = tfer.data[0]
                lm_tfer = LM73Transfer(tfer.address, LM73Operation.WriteData, \
                    cur_reg, tfer.data[1:])

        else: # Read data
            lm_tfer = LM73Transfer(tfer.address, LM73Operation.ReadData, cur_reg, tfer.data)

        lm_tfer.i2c_tfer = tfer
        yield lm_tfer

