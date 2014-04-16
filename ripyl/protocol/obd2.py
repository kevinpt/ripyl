#!/usr/bin/python
# -*- coding: utf-8 -*-

'''OBD-2 protocol support
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

import inspect

from ripyl.decode import *
from ripyl.streaming import *
from ripyl.util.enum import Enum
from ripyl.util.bitops import split_bits

class OBD2MsgType(Enum):
    '''Enumeration for message types'''
    Request = 0
    Response = 1
    Unknown = 2


class OBD2Message(object):
    '''Abstract base class for OBD-2 messages

    This is to be specialized in each protocol implementation.
    '''
    def __init__(self, msg_type):
        self.msg_type = msg_type


    def checksum_good(self):
        '''Validate the message checksum

        Returns a bool that is True when checksum is valid.
        '''
        raise NotImplementedError

    def raw_data(self, full_message=False):
        '''Get the raw data for the message

        full_message (bool)
            Returns complete message including header and checksum when true

        Returns a list of bytes.
        '''
        raise NotImplementedError


    @property
    def start_time(self):
        '''Message start time'''
        raise NotImplementedError

    @property
    def end_time(self):
        '''Message end time'''
        raise NotImplementedError

        

class OBD2StreamMessage(StreamSegment):
    '''Encapsulates an OBD2Message object into a StreamSegment'''

    def __init__(self, msg, status=StreamStatus.Ok):
        '''
        bounds ((float, float))
            2-tuple (start_time, end_time) for the packet
            
        msg (OBD2Message)
            OBD2Message object to wrap in a StreamSegment

        status (int)
            Status code for the packet

        '''
        StreamSegment.__init__(self, (None, None), status=status)
        self.data = msg

        self.kind = 'OBD-2 message'

    @classmethod
    def status_text(cls, status):
        return StreamSegment.status_text(status)

    @property
    def msg(self):
        return self.data

    @property
    def start_time(self):
        '''Message start time'''
        return self.msg.start_time

    @start_time.setter
    def start_time(self, value):
        pass

    @property
    def end_time(self):
        '''Message end time'''
        return self.msg.end_time

    @end_time.setter
    def end_time(self, value):
        pass

    def __repr__(self):
        status_text = OBD2StreamMessage.status_text(self.status)
        return 'OBD2StreamMessage({}, {})'.format(self.msg, status_text)



class OBD2StreamTransfer(StreamSegment):
    '''Represent a collection of messages involved in a request/response transaction.'''
    def __init__(self, messages, status=StreamStatus.Ok):
        '''
        messages (sequence of OBD2StreamMessage)
            A sequence of OBD2StreamMessage objects that form a transfer
        '''
        StreamSegment.__init__(self, (None, None), status=status)
        self.subrecords = messages
        self.kind = 'OBD-2 transfer'

    @property
    def start_time(self):
        return self.subrecords[0].start_time

    @start_time.setter
    def start_time(self, value):
        pass

    @property
    def end_time(self):
        return self.subrecords[-1].end_time

    @end_time.setter
    def end_time(self, value):
        pass



def reconstruct_obd2_transfers(records):
    '''Aggregate a stream of OBD2StreamMessage objects into OBD2StreamTransfers.

    A transfer consists of a request message followed by 0 or more responses from
    each ECU on the bus. A new transfer starts with every request message. Objects
    other than OBD2StreamMessage are passed through unchanged

    records (sequence of OBD2StreamMessage)
        The message objects to reconstruct the transfers from.

    Yields a stream of OBD2StreamTransfer objects containing aggregated messages
      from the input records and any additional non-message stream objects.
    '''
    tfer_msgs = []

    for r in records:
        if isinstance(r, OBD2StreamMessage):
            if r.msg.msg_type == OBD2MsgType.Request:
                if len(tfer_msgs) > 0:
                    # yield the last transfer
                    yield OBD2StreamTransfer(tfer_msgs)

                tfer_msgs = [r] # start a new transfer
                
            else: # response
                # Add it to the list of transfers
                tfer_msgs.append(r)


        else: # not an OBD-2 message object
            if len(tfer_msgs) > 0:
                # yield the last transfer
                yield OBD2StreamTransfer(tfer_msgs)
                tfer_msgs = []

            # yield the object
            yield r

    if len(tfer_msgs) > 0:
        # yield the last transfer
        yield OBD2StreamTransfer(tfer_msgs)
    


#### OBD-2 message decoding

obd2_command_decoders = {}

def decode_obd2_command(msg_type, raw_data):
    '''Decode the contents of an OBD-2 message

    msg_type (OBD2MsgType)
        The type of message (request or response) to be decoded.

    raw_data (sequence of ints)
        The bytes forming the message

    Returns a 3-tuple containing a string description, a parameter value, and a string for
      parameter units. The parameter value is None for request messages and for response
      messages with no defined decode routine.
    '''
    result = None
    for de in _obd2_command_decoders.itervalues():
        result = de(msg_type, raw_data)
        if result is not None:
            break

    return result

def register_command_decoder(name, func):
    '''Add a decoder function for additional manufacturer specific SIDs

    name (string)
        The name of the command set to register the decoder under.

    func (function(OBD2MsgType, (int,...)))
        A Python function object that will be called as a command decoder.
    '''
    if name not in _obd2_command_decoders.iterkeys():
        _obd2_command_decoders[name] = func


sid_decoders = {}

def _obd2_std_command_decoder(msg_type, raw_data):
    '''Decode the standard OBD-2 SIDs defined in the J1979 standard
    msg_type (OBD2MsgType)
        The type of message (request or response) to be decoded.

    raw_data (sequence of ints)
        The bytes forming the message
    '''
    sid = raw_data[0]
    if msg_type == OBD2MsgType.Response:
        sid -= 0x40


    if sid in sid_decoders.iterkeys():
        return sid_decoders[sid](msg_type, raw_data)
    else:
        return None

_obd2_command_decoders = {'obd-2 standard': _obd2_std_command_decoder}




def _get_supported_pids(offset, a, b, c, d):
    '''Decode the response to SID 0x01 PID 0x00, 0x20, 0x40, 0x60 requests

    offset (int)
        The offset for the PID (0x00, 0x20, etc.)

    a,b,c,d (sequence of ints)
        The four bytes of the response

    Returns a sequence of integers for each suported PID.
    '''
    merged_code = ((a*256 + b)*256 +c)*256 + d
    pid_bits = split_bits(merged_code, 32)

    pids = []
    for i, b in enumerate(pid_bits):
        if b == 1:
            pids.append(i+1+offset)

    return pids

def _get_status(a, b, c, d):
    '''Decode response for sid 0x01, pid 0x01'''
    r = {}
    r['DTC count'] = a & 0x7F
    r['MIL status'] = True if a & 0x80 else False

    r['spark ignition'] = False if b & 0x08 else True
    test_available = [bool(v) for v in split_bits(b & 0x07, 3)]
    test_incomplete = [bool(v) for v in split_bits((b & 0x70) >> 4, 3)]
    common_tests = ['misfire', 'fuel system', 'components']
    tests = {}
    for tname, ta, tc in zip(common_tests, test_available, test_incomplete):
        #print('## test', tname, ta, tc)
        tests[tname] = (ta, tc)

    if r['spark ignition']:
        spark_tests = ['catalyst', 'heated catalyst', 'evap. system', \
            'secondary air system', 'A/C refrigerant', 'oxygen sensor', \
            'oxygen sensor heater', 'EGR system']
        test_available = [bool(v) for v in split_bits(c, 8)]
        test_incomplete = [bool(v) for v in split_bits(d, 8)]
        #print('## ta', test_available, test_complete)

        for tname, ta, tc in zip(spark_tests, test_available, test_incomplete):
            #print('## test', tname, ta, tc)
            tests[tname] = (ta, tc)
        
    else: #compression
        compression_tests = [('NMHC cat', 0), ('NOx/SCR meter', 1), ('boost pressure', 3), \
            ('exhaust gas sensor', 5), ('PM filter monitoring', 6), ('EGR and/or VVT system', 7)]


        test_available = [bool(v) for v in reversed(split_bits(c, 8))]
        test_incomplete = [bool(v) for v in reversed(split_bits(d, 8))]

        for tname, i in compression_tests:
            #print('## test', tname, test_available[i], test_incomplete[i])
            tests[tname] = (test_available[i], test_incomplete[i])
    
    r['tests'] = tests

    return r


def decode_dtc(dtc):
    '''Convert encoded DTC to a string

    dtc (int)
        The binary coded DTC.

    Returns a string representing the DTC in readable form.
    '''

    class_codes = {0: 'P', 1:'C', 2:'B', 3:'U'}
    dtc_class = class_codes[(dtc >> 14) & 0x3]
    digits = [(dtc >> 12) & 0x3, (dtc >> 8) & 0xF, (dtc >> 4) & 0xF, dtc & 0xF]
    # convert BCD to hex
    h_digits = ['{:X}'.format(d) for d in digits]
    
    return dtc_class + ''.join(h_digits)    


def _get_freeze_dtc(a, b):
    '''Decode response for sid 0x01, pid 0x02'''
    code = a*256 + b
    if code > 0:
        return decode_dtc(code)
    else:
        return None

def _get_fuel_status(a, b):
    '''Decode response for sid 0x01, pid 0x03'''
    r = {}

    status_codes = ['Open loop due to insufficient engine temperature', \
        'Closed loop, using oxygen sensor feedback to determine fuel mix', \
        'Open loop due to engine load OR fuel cut due to deceleration', \
        'Open loop due to system failure', \
        'Closed loop, using at least one oxygen sensor but there is a fault in the feedback system']

    for system, byte in [('fuel1', a), ('fuel2', b)]:
        # decode the status. This is a one-hot encoding in bits 0-4
        if byte & 0x01:
            r[system] = status_codes[0]
        elif byte & 0x02:
            r[system] = status_codes[1]
        elif byte & 0x04:
            r[system] = status_codes[2]
        elif byte & 0x08:
            r[system] = status_codes[3]
        elif byte & 0x10:
            r[system] = status_codes[4]

    return r

def _get_sai_status(a):
    '''Decode response for sid 0x01, pid 0x12'''
    status_codes = ['Upstream of catalytic converter', \
        'Downstream of catalytic converter', \
        'From the outside atmosphere or off' ]
    r = None

    if a & 0x01:
        r = status_codes[0]
    elif a & 0x02:
        r = status_codes[1]
    elif a & 0x04:
        r = status_codes[2]

    return r

def _get_o2_sensors_13(a):
    '''Decode response from sid 0x01, pid 0x13'''

    sensors = {
        'b1s1': False, 'b1s2': False, 'b1s3': False, 'b1s4': False,
        'b2s1': False, 'b2s2': False, 'b2s3': False, 'b2s4': False,
    }

    if a & 0x01: sensors['b1s1'] = True
    if a & 0x02: sensors['b1s2'] = True
    if a & 0x04: sensors['b1s3'] = True
    if a & 0x08: sensors['b1s4'] = True

    if a & 0x10: sensors['b2s1'] = True
    if a & 0x20: sensors['b2s2'] = True
    if a & 0x40: sensors['b2s3'] = True
    if a & 0x80: sensors['b2s4'] = True

    return sensors


_obd2_standards = {
    0x01: 'OBD-II as defined by the CARB',
    0x02: 'OBD as defined by the EPA',
    0x03: 'OBD and OBD-II',
    0x04: 'OBD-I',
    0x05: 'Not meant to comply with any OBD standard',
    0x06: 'EOBD (Europe)',
    0x07: 'EOBD and OBD-II',
    0x08: 'EOBD and OBD',
    0x09: 'EOBD, OBD and OBD II',
    0x0A: 'JOBD (Japan)',
    0x0B: 'JOBD and OBD II',
    0x0C: 'JOBD and EOBD',
    0x0D: 'JOBD, EOBD, and OBD II'
}

def _get_supported_standards(a):
    '''Decode response from sid 0x01, pid 0x1C'''

    if a in _obd2_standards.iterkeys():
        return _obd2_standards[a]
    else:
        return 'unknown'

def _get_o2_sensors_1d(a):
    '''Decode response from sid 0x01, pid 0x1D'''

    sensors = {
        'b1s1': False, 'b1s2': False, 'b2s1': False, 'b2s2': False,
        'b3s1': False, 'b3s2': False, 'b4s1': False, 'b4s2': False,
    }

    if a & 0x01: sensors['b1s1'] = True
    if a & 0x02: sensors['b1s2'] = True
    if a & 0x04: sensors['b2s1'] = True
    if a & 0x08: sensors['b2s2'] = True

    if a & 0x10: sensors['b3s1'] = True
    if a & 0x20: sensors['b3s2'] = True
    if a & 0x40: sensors['b4s1'] = True
    if a & 0x80: sensors['b4s2'] = True

    return sensors


def _get_drive_cycle_status(a, b, c, d):
    '''Decode response for sid 0x01, pid 0x41'''

    test_available = [bool(v) for v in split_bits(b & 0x0F, 4)]
    test_incomplete = [bool(v) for v in split_bits((b & 0xF0) >> 4, 4)]
    b_tests = ['misfire', 'fuel system', 'components', 'reserved_in_b']

    tests = {}
    for tname, ta, tc in zip(b_tests, test_available, test_incomplete):
        tests[tname] = (ta, tc)


    test_available = [bool(v) for v in split_bits(c, 8)]
    test_incomplete = [bool(v) for v in split_bits(d, 8)]
    
    spark_tests = ['catalyst', 'heated catalyst', 'evap. system', \
        'secondary air system', 'A/C refrigerant', 'oxygen sensor', \
        'oxygen sensor heater', 'EGR system']

    for tname, ta, tc in zip(spark_tests, test_available, test_incomplete):
        tests[tname] = (ta, tc)
    
    return tests


class PIDTableEntry(object):
    '''Data structure for string PID decode info'''
    def __init__(self, bytes_returned, description, units='', decoder=None):
        self.bytes_returned = bytes_returned
        self.description = description
        self.units = units
        self.decoder = decoder

PTE = PIDTableEntry


sid_01_pids = {
    0x00 : PTE(4, 'PIDs supported [01 - 20]', '', lambda a, b, c, d: _get_supported_pids(0x00, a, b, c, d)),
    0x01 : PTE(4, 'Monitor status since DTCs cleared', '', lambda a, b, c, d: _get_status(a, b, c, d)),
    0x02 : PTE(2, 'Freeze DTC', '', lambda a, b: _get_freeze_dtc(a, b)),
    0x03 : PTE(2, 'Fuel system status', '', lambda a, b: _get_fuel_status(a, b)),
    0x04 : PTE(1, 'Calculated engine load value', '%', lambda a: a*100.0/255.0),
    0x05 : PTE(1, 'Engine coolant temperature', 'C', lambda a: a-40.0),
    0x06 : PTE(1, 'Short term fuel % trim-Bank 1', '%', lambda a: (a-128)*100.0/128.0),
    0x07 : PTE(1, 'Long term fuel % trim-Bank 1', '%', lambda a: (a-128)*100.0/128.0),
    0x08 : PTE(1, 'Short term fuel % trim-Bank 2', '%', lambda a: (a-128)*100.0/128.0),
    0x09 : PTE(1, 'Long term fuel % trim-Bank 2', '%', lambda a: (a-128)*100.0/128.0),
    0x0A : PTE(1, 'Fuel pressure', 'kPa', lambda a: a*3.0),
    0x0B : PTE(1, 'Intake manifold absolute pressure', 'kPa', lambda a: float(a)),
    0x0C : PTE(2, 'Engine RPM', 'rpm', lambda a, b: (a*256 + b)/4.0),
    0x0D : PTE(1, 'Vehicle speed', 'km/h', lambda a: float(a)),
    0x0E : PTE(1, 'Timing advance', 'degrees', lambda a: a/2.0 - 64.0),
    0x0F : PTE(1, 'Intake air temperature', 'C', lambda a: a-40.0),

    0x10 : PTE(2, 'MAF air flow rate', 'g/s', lambda a, b: (a*256 + b) / 100.0),
    0x11 : PTE(1, 'Throttle position', '%', lambda a: a*100.0/255.0),
    0x12 : PTE(1, 'Commanded secondary air status', '', lambda a: _get_sai_status(a)),
    0x13 : PTE(1, 'Oxygen sensors present', '', lambda a: _get_o2_sensors_13(a)),
    0x14 : PTE(2, 'Bank 1, Sensor 1: Oxygen sensor voltage, Short term fuel trim', ('V', '%'), lambda a, b: (a/200.0, None if b == 0xFF else (b-128)*100.0/128.0)),
    0x15 : PTE(2, 'Bank 1, Sensor 2: Oxygen sensor voltage, Short term fuel trim', ('V', '%'), lambda a, b: (a/200.0, None if b == 0xFF else (b-128)*100.0/128.0)),
    0x16 : PTE(2, 'Bank 1, Sensor 3: Oxygen sensor voltage, Short term fuel trim', ('V', '%'), lambda a, b: (a/200.0, None if b == 0xFF else (b-128)*100.0/128.0)),
    0x17 : PTE(2, 'Bank 1, Sensor 4: Oxygen sensor voltage, Short term fuel trim', ('V', '%'), lambda a, b: (a/200.0, None if b == 0xFF else (b-128)*100.0/128.0)),
    0x18 : PTE(2, 'Bank 2, Sensor 1: Oxygen sensor voltage, Short term fuel trim', ('V', '%'), lambda a, b: (a/200.0, None if b == 0xFF else (b-128)*100.0/128.0)),
    0x19 : PTE(2, 'Bank 2, Sensor 2: Oxygen sensor voltage, Short term fuel trim', ('V', '%'), lambda a, b: (a/200.0, None if b == 0xFF else (b-128)*100.0/128.0)),
    0x1A : PTE(2, 'Bank 2, Sensor 3: Oxygen sensor voltage, Short term fuel trim', ('V', '%'), lambda a, b: (a/200.0, None if b == 0xFF else (b-128)*100.0/128.0)),
    0x1B : PTE(2, 'Bank 2, Sensor 4: Oxygen sensor voltage, Short term fuel trim', ('V', '%'), lambda a, b: (a/200.0, None if b == 0xFF else (b-128)*100.0/128.0)),
    0x1C : PTE(1, 'OBD standards this vehicle conforms to', '', lambda a: _get_supported_standards(a)),
    0x1D : PTE(1, 'Oxygen sensors present', '', lambda a: _get_o2_sensors_1d(a)),
    0x1E : PTE(1, 'Auxiliary input status', '', lambda a: {'PTO active': bool(a & 0x01)}),
    0x1F : PTE(2, 'Run time since engine start', 's', lambda a, b: a*256 + b),

    0x20 : PTE(4, 'PIDs supported [21 - 40]', '', lambda a, b, c, d: _get_supported_pids(0x20, a, b, c, d)),
    0x21 : PTE(2, 'Distance traveled with malfunction indicator lamp (MIL) on', 'km', lambda a, b: a*256 + b),
    0x22 : PTE(2, 'Fuel Rail Pressure (relative to manifold vacuum)', 'kPa', lambda a, b: (a*256 + b) * 0.079),
    0x23 : PTE(2, 'Fuel Rail Pressure (diesel, or gasoline direct inject)', 'kPa', lambda a, b: (a*256 + b) * 10.0),
    0x24 : PTE(4, 'O2S1: Equivalence Ratio, Voltage', ('', 'V'), lambda a, b, c, d: ((a*256+b) / 32768.0, (c*256+d) / 8192.0)),
    0x25 : PTE(4, 'O2S2: Equivalence Ratio, Voltage', ('', 'V'), lambda a, b, c, d: ((a*256+b) / 32768.0, (c*256+d) / 8192.0)),
    0x26 : PTE(4, 'O2S3: Equivalence Ratio, Voltage', ('', 'V'), lambda a, b, c, d: ((a*256+b) / 32768.0, (c*256+d) / 8192.0)),
    0x27 : PTE(4, 'O2S4: Equivalence Ratio, Voltage', ('', 'V'), lambda a, b, c, d: ((a*256+b) / 32768.0, (c*256+d) / 8192.0)),
    0x28 : PTE(4, 'O2S5: Equivalence Ratio, Voltage', ('', 'V'), lambda a, b, c, d: ((a*256+b) / 32768.0, (c*256+d) / 8192.0)),
    0x29 : PTE(4, 'O2S6: Equivalence Ratio, Voltage', ('', 'V'), lambda a, b, c, d: ((a*256+b) / 32768.0, (c*256+d) / 8192.0)),
    0x2A : PTE(4, 'O2S7: Equivalence Ratio, Voltage', ('', 'V'), lambda a, b, c, d: ((a*256+b) / 32768.0, (c*256+d) / 8192.0)),
    0x2B : PTE(4, 'O2S8: Equivalence Ratio, Voltage', ('', 'V'), lambda a, b, c, d: ((a*256+b) / 32768.0, (c*256+d) / 8192.0)),
    0x2C : PTE(1, 'Commanded EGR', '%', lambda a: a*100.0/255.0),
    0x2D : PTE(1, 'EGR Error', '%', lambda a: (a-128)*100.0/128.0),
    0x2E : PTE(1, 'Commanded evaporative purge', '%', lambda a: a*100.0/255.0),
    0x2F : PTE(1, 'Fuel Level Input', '%', lambda a: a*100.0/255.0),

    0x30 : PTE(1, '# of warm-ups since codes cleared', '', lambda a: a),
    0x31 : PTE(2, 'Distance traveled since codes cleared', 'km', lambda a, b: a*256 + b),
    0x32 : PTE(2, 'Evap. System Vapor Pressure', 'Pa', lambda a, b: ((a if a <= 127 else a-256)*256+(b if b <= 127 else b-256))/4.0),
    0x33 : PTE(1, 'Barometric pressure', 'kPa', lambda a: float(a)),
    0x34 : PTE(4, 'O2S1: Equivalence Ratio, Current', ('', 'mA'), lambda a, b, c, d: ((a*256+b)/32768.0, (a*256+b)/256.0 - 128.0)),
    0x35 : PTE(4, 'O2S2: Equivalence Ratio, Current', ('', 'mA'), lambda a, b, c, d: ((a*256+b)/32768.0, (a*256+b)/256.0 - 128.0)),
    0x36 : PTE(4, 'O2S3: Equivalence Ratio, Current', ('', 'mA'), lambda a, b, c, d: ((a*256+b)/32768.0, (a*256+b)/256.0 - 128.0)),
    0x37 : PTE(4, 'O2S4: Equivalence Ratio, Current', ('', 'mA'), lambda a, b, c, d: ((a*256+b)/32768.0, (a*256+b)/256.0 - 128.0)),
    0x38 : PTE(4, 'O2S5: Equivalence Ratio, Current', ('', 'mA'), lambda a, b, c, d: ((a*256+b)/32768.0, (a*256+b)/256.0 - 128.0)),
    0x39 : PTE(4, 'O2S6: Equivalence Ratio, Current', ('', 'mA'), lambda a, b, c, d: ((a*256+b)/32768.0, (a*256+b)/256.0 - 128.0)),
    0x3A : PTE(4, 'O2S7: Equivalence Ratio, Current', ('', 'mA'), lambda a, b, c, d: ((a*256+b)/32768.0, (a*256+b)/256.0 - 128.0)),
    0x3B : PTE(4, 'O2S8: Equivalence Ratio, Current', ('', 'mA'), lambda a, b, c, d: ((a*256+b)/32768.0, (a*256+b)/256.0 - 128.0)),
    0x3C : PTE(2, 'Catalyst Temperature Bank 1, Sensor 1', 'C', lambda a, b: (a*256+b)/10.0 -40.0),
    0x3D : PTE(2, 'Catalyst Temperature Bank 1, Sensor 2', 'C', lambda a, b: (a*256+b)/10.0 -40.0),
    0x3E : PTE(2, 'Catalyst Temperature Bank 2, Sensor 1', 'C', lambda a, b: (a*256+b)/10.0 -40.0),
    0x3F : PTE(2, 'Catalyst Temperature Bank 2, Sensor 2', 'C', lambda a, b: (a*256+b)/10.0 -40.0),

    0x40 : PTE(4, 'PIDs supported [41 - 60]', '', lambda a, b, c, d: _get_supported_pids(0x40, a, b, c, d)),
    0x41 : PTE(4, 'Monitor status this drive cycle', '', lambda a, b, c, d: _get_drive_cycle_status(a, b, c, d)),
    0x42 : PTE(2, 'Control module voltage', 'V', lambda a, b: (a*256+b)/1000.0),
    0x43 : PTE(2, 'Absolute load value', '%', lambda a, b: (a*256+b)*100.0/255.0),
    0x44 : PTE(2, 'Command equivalence ratio', '', lambda a, b: (a*255+b)/32768.0),
    0x45 : PTE(1, 'Relative throttle position', '%', lambda a: a*100.0/255.0),
    0x46 : PTE(1, 'Ambient air temperature', 'C', lambda a: a-40.0),
    0x47 : PTE(1, 'Absolute throttle position B', '%', lambda a: a*100.0/255.0),
    0x48 : PTE(1, 'Absolute throttle position C', '%', lambda a: a*100.0/255.0),
    0x49 : PTE(1, 'Absolute throttle position D', '%', lambda a: a*100.0/255.0),
    0x4A : PTE(1, 'Absolute throttle position E', '%', lambda a: a*100.0/255.0),
    0x4B : PTE(1, 'Absolute throttle position F', '%', lambda a: a*100.0/255.0),
    0x4C : PTE(1, 'Commanded throttle actuator', '%', lambda a: a*100.0/255.0),
    0x4D : PTE(2, 'Time run with MIL on', 'min.', lambda a, b: a*256+b),
    0x4E : PTE(2, 'Time since trouble codes cleared', 'min.', lambda a, b: a*256+b),
    0x4F : PTE(4, 'Maximum value for equivalence ratio, oxygen sensor voltage, oxygen sensor current, and intake manifold absolute pressure', ('', 'V', 'mA', 'kPa'), lambda a, b, c, d: (a,b,c,d*10.0)),

}


sid_02_pids = {
    0x02 : PTE(2, 'Freeze frame trouble code')
}



def _decode_obd_msg(sid, pid_table, msg_type, raw_data):
    '''Generic decode of standard OBD-2 messages'''
    pid = raw_data[1]
    if pid in pid_table.iterkeys():
        te = pid_table[pid]
        summary = 'sid: {:02x}, pid: {:02x}, "{}"'.format(sid, pid, te.description)
        value = None
        if msg_type == OBD2MsgType.Response and len(raw_data) == te.bytes_returned + 2 \
            and te.decoder is not None:
            # get number of arguments
            arg_num = len(inspect.getargspec(te.decoder).args)
            value = te.decoder(*raw_data[2:2+arg_num])
        
        return (summary, value, te.units)
    else:
        return None

    

def _decode_obd_sid_03_msg(msg_type, raw_data):
    '''Decode of OBD-2 SID 0x03 messages'''
    summary = 'sid: 03, "Request trouble codes"'
    if msg_type == OBD2MsgType.Response:
        # Get DTC codes from response data
        raw_dtcs = raw_data[1:]
        # Always six bytes in response representing 0 - 3 DTCs
        # Unused DTC slots are 0x0000

        dtc_codes = [raw_dtcs[i]*256+raw_dtcs[i+1] for i in (0, 2, 4)]
        dtcs = []
        for code in dtc_codes:
            if code != 0x0000:
                dtcs.append(decode_dtc(code))

        return (summary, dtcs, '')
        
    else:
        return (summary, None, '')


def _decode_obd_sid_04_msg(msg_type, raw_data):
    '''Decode of OBD-2 SID 0x04 messages'''
    return ('sid: 04, "Clear trouble codes"', None, '')


_neg_response_codes = {
    0x00: 'cancel acknowledge', # Sagem extension??
    0x10: 'general reject',
    0x11: 'service not supported',
    0x12: 'sub-function not supported',
    0x21: 'busy',
    0x22: 'conditions not correct',
    0x78: 'response pending'
}

def _decode_obd_neg_response(msg_type, raw_data):
    # decode negative response codes defined in J1979 4.2.4
    if msg_type == OBD2MsgType.Response:
        req_sid = raw_data[1]
        response_code = raw_data[2]

        if response_code in _neg_response_codes.iterkeys():
            rc_text = _neg_response_codes[response_code]
        else:
            rc_text = 'unknown (0x{:02x})'.format(response_code)

        summary = 'sid: 7F, req: {}, "Negative response: {}"'.format(req_sid, rc_text)
    else:
        summary = 'sid: 3F, "Cancel request"' # Sagem extension??

    return (summary, None, '')

sid_decoders = {
    0x01: lambda mtype, d: _decode_obd_msg(0x01, sid_01_pids, mtype, d),
    0x02: lambda mtype, d: _decode_obd_msg(0x02, sid_02_pids, mtype, d),
    0x03: _decode_obd_sid_03_msg,
    0x04: _decode_obd_sid_04_msg,
    0x3F: _decode_obd_neg_response # Only used as response 0x7F
}

# NOTE: ISO14229 has additional SIDs

# SID 0x11 ECU reset
# SID 0x27 Security access

