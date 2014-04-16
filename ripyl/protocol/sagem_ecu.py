#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Sagem ECU protocol support

    This module should be included along with ripyl.protocol.obd2.
    The Sagem decode functions will be registered with the OBD-2 decoder
    and are accessed through obd2.decode_obd2_command().
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
import ripyl.protocol.obd2 as obd

sag_sid_decoders = {}

def _sagem_command_decoder(msg_type, raw_data):
    # Decode the SIDs for the Sagem ECU
    sid = raw_data[0]
    if msg_type == obd.OBD2MsgType.Response:
        sid -= 0x40


    if sid in sag_sid_decoders.iterkeys():
        return sag_sid_decoders[sid](msg_type, raw_data)
    else:
        return None


obd.register_command_decoder('Sagem ECU', _sagem_command_decoder)



PTE = obd.PIDTableEntry

sid_21_pids = {
    0x80: PTE(33, 'ECU identification', '')
}

sid_22_pids = {
    0x0001: PTE(2, 'Temp. sensor voltage???', 'V', lambda a, b: (a*256+b) / 51.0),
    0x0002: PTE(2, 'Temp. sensor voltage???', 'V', lambda a, b: (a*256+b) / 51.0),
    0x0003: PTE(2, 'Engine temperature', 'C', lambda a, b: (a*256+b) - 40.0),
    0x0004: PTE(2, 'Manifold air temp.', 'C', lambda a, b: (a*256+b) - 40.0),
    0x0005: PTE(2, '???', '%', lambda a, b: (a*256+b)*1.28 - 100.0),
    0x0007: PTE(2, 'Airbox pressure', 'hPa', lambda a, b: (a*256+b) / 50.0),
    0x0008: PTE(2, 'Spark advance (angle BTDC)', 'degrees', lambda a, b: (a*256+b) / 2.0 - 64.0),
    0x0009: PTE(2, 'indicator???', '', lambda a, b: (a*256+b)),
    0x000A: PTE(2, 'indicator???', '', lambda a, b: (a*256+b)),
    0x000F: PTE(2, 'Neutral switch', '', lambda a, b: (a*256+b) ^ 0xFF), # Byte b: 0=neutral, 0xff=in gear
    0x0015: PTE(2, 'Battery voltage', 'V', lambda a, b: (a*256+b) * 0.1),
    0x0017: PTE(2, 'TPS', '%'),
    0x0018: PTE(2, 'TPS voltage', 'V', lambda a, b: (a*256+b) / 51.0),
    0x001A: PTE(2, 'Engine load', '%', lambda a, b: (a*256+b)*100.0 / 255.0),
    0x003B: PTE(2, 'RPM', 'rpm', lambda a, b: (a*256+b) / 40.0 * 10.0),
    0x004C: PTE(2, 'Coil 1 dwell', 's', lambda a, b: (a*256+b) / 312.0),
    0x004D: PTE(2, 'Coil 2 dwell', 's', lambda a, b: (a*256+b) / 312.0),
    0x004E: PTE(2, 'Coil 3 dwell', 's', lambda a, b: (a*256+b) / 312.0),
    0x004F: PTE(2, 'Coil 4 dwell', 's', lambda a, b: (a*256+b) / 312.0),
    0x012C: PTE(2, 'O2 sensor???', '', lambda a, b: (a*256+b)),
    0x0405: PTE(2, 'Injector 1 pulse width', 's', lambda a, b: (a*256+b) / 312.0),
    0x0406: PTE(2, 'Injector 2 pulse width', 's', lambda a, b: (a*256+b) / 312.0),
    0x0407: PTE(2, 'Injector 3 pulse width', 's', lambda a, b: (a*256+b) / 312.0),
    0x0408: PTE(2, 'Injector 4 pulse width', 's', lambda a, b: (a*256+b) / 312.0),
    0x2332: PTE(2, 'Long term fuel trim', '%', lambda a, b: a / 1.28 - 100.0 + b / 327.68),
    0x2335: PTE(2, 'throttle???', '', lambda a, b: (147.0 - (a*256+b)) * 0.1 if (a*256+b) >= 147 else 0.0),
    0x2337: PTE(2, 'IACV offset???', '', lambda a, b: (a*256+b) / 1.28 - 100.0),
    0x2346: PTE(2, '???', '', lambda a, b: (a*256+b) * 10.0)
}

# Security access mode
sid_27_pids = {
    0x0302: PTE(2, 'Unlock Sagem extensions', '')
}

sid_3C_pids = {
    0x03: PTE(5, 'Query ID 1???', ''),
    0x04: PTE(2, 'Query ID 2???', ''),
    0x08: PTE(5, 'ECU serial number', '')
}


def decode_sagem_msg(sid, pid_table, pid_size, msg_type, raw_data):
    '''Decode SAGEM message with one or two byte PIDs

    sid (int)
        The message SID

    pid_table (dict of PIDTableEntry)
        A dict associating PIDs with decode information

    pid_size (int)
        The number of bytes in the PID: 1 or 2

    msg_type (OBD2MsgType)
        Request or response message

    raw_data (sequence of ints)
        Bytes for the message

    '''
    if pid_size == 2:
        pid = raw_data[1]*256 + raw_data[2]
    else:
        pid = raw_data[1]

    if pid in pid_table.iterkeys():
        te = pid_table[pid]
        summary = 'sid: {:02x}, pid: {:0{}x}, "{}"'.format(sid, pid, 2*pid_size, te.description)
        value = None
        if msg_type == obd.OBD2MsgType.Response and len(raw_data) == te.bytes_returned + 1 + pid_size \
            and te.decoder is not None:
            # get number of arguments
            arg_num = len(inspect.getargspec(te.decoder).args)
            value = te.decoder(*raw_data[1+pid_size:1+pid_size+arg_num])
        
        return (summary, value, te.units)
    else:
        return None


sag_sid_decoders = {
    0x21: lambda mtype, d: decode_sagem_msg(0x21, sid_21_pids, 1, mtype, d),
    0x22: lambda mtype, d: decode_sagem_msg(0x22, sid_22_pids, 2, mtype, d),
    0x27: lambda mtype, d: decode_sagem_msg(0x27, sid_27_pids, 2, mtype, d),
    0x3C: lambda mtype, d: decode_sagem_msg(0x3C, sid_3C_pids, 1, mtype, d)
}


