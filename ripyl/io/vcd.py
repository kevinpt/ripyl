#!/usr/bin/python
# -*- coding: utf-8 -*-

'''VCD file I/O
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

import datetime
import math
import ripyl
import ripyl.util.eng as eng
import ripyl.decode as decode


_vcd_identifiers = [chr(n) for n in xrange(33, 127)]

_vcd_si_prefixes = {
    0:   '',
    -3:  'm',
    -6:  'u',
    -9:  'n',
    -12: 'p',
    -15: 'f'
}

class VCDChannel(object):
    '''A VCD channel definition'''
    def __init__(self, name, states, bits=1, vtype='wire'):
        '''
        name (string)
            The name of this channel

        states (sequence of (float, int))
            The states for the channel. This can be an edge sequence or a
            similar sequence containing numeric values

        bits (int)
            The number of bits in the channel

        vtype (string)
            The var_type for the channel
        '''
        self.name = name
        self.vtype = vtype
        self.bits = bits
        self.states = states


def coerce_timescale(ts):
    '''Coerce the timescale to a valid value'''
    e_num, e_exp = eng.Eng(ts)._to_eng()
    i_mag = 10 ** int(math.log10(e_num))

    return float(i_mag) * 10.0 ** e_exp


class VCDInfo(object):
    '''A VCD info object'''
    def __init__(self, channels, timescale=1.0e-12, date=None, comment=None):
        '''
        channels (sequence of VCDChannel)
            A sequence of channel definitions

        timescale (float or string)
            Set the VCD timescale as a power of 10.
            If a float, the value is used to establish the timescale.
            If a string, it must match a channel name from channels. The symbol rate
            of the named channel is determined and a raw timescale is derived from
            1.0 / (4 * symbol rate). In both cases the raw value will be coerced to
            a valid power of 10.

        date (datetime or None)
            An optional datetime for the VCD header. If absent the current time is used.

        comment (string or None)
            An optional comment to include in the header.

        Raises ValueError if the timescale channel cannot be found or the symbol rate cannot
          be determined.
        '''
        self._date = date
        self.comment = comment
        self.channels = channels

        try:
            ts = float(timescale)
        except ValueError: # Assume it's a string
            # Find channel name in channels
            ts_data = None
            for c in self.channels:
                if c.name == timescale:
                    ts_data = c.states
                    break

            if ts_data is not None:
                sym_rate = decode.find_symbol_rate(iter(ts_data))
                if sym_rate == 0:
                    raise ValueError('Unable to determine automatic timescale')

                ts = 1.0 / (4 * sym_rate)
            else:
                raise ValueError('Channel not found: "{}"'.format(timescale))

        self._timescale = coerce_timescale(ts)


    @property
    def date(self):
        if self._date is None:
            return datetime.datetime.now()
        else:
            return self._date

    @date.setter
    def date(self, value):
        self._date = value


    @property
    def timescale(self):
        return self._timescale

    @timescale.setter
    def timescale(self, value):
        self._timescale = coerce_timescale(value)


    @property
    def timescale_si(self):
        '''Convert timescale float to a string with SI units'''
        e_num, e_exp = eng.Eng(self.timescale)._to_eng()
        i_mag = 10 ** int(math.log10(e_num))

        return '{} {}s'.format(i_mag, _vcd_si_prefixes[e_exp])

    def write(self, fname, init_with_dumpvars=False):
        '''Write a VCD file

        fname (string)
            The name of the file to write to
        '''
        with open(fname, 'w') as fh:
            # Write the header
            fh.write('$date\n  {}\n$end\n'.format(str(self.date)))
            fh.write('$version\n  Ripyl {} VCD dump\n$end\n'.format(ripyl.__version__))
            if self.comment is not None:
                comment_block = '\n'.join(['  ' + ln for ln in self.comment.split('\n')])
                fh.write('$comment\n{}\n$end\n'.format(comment_block))

            fh.write('$timescale  {}  $end\n'.format(self.timescale_si))

            # Variable definitions
            fh.write('$scope module logic $end\n')
            for i, c in enumerate(self.channels):
                fh.write('$var  {} {} {} {}  $end\n'.format(c.vtype, c.bits, _vcd_identifiers[i], c.name))
            fh.write('$upscope $end\n')

            fh.write('$enddefinitions $end\n')

            # Initial values
            if init_with_dumpvars:
                fh.write('$dumpvars\n')
            else:
                fh.write('#0\n')

            prev_states = {}
            for i, c in enumerate(self.channels):
                if c.bits > 1:
                    state = 'b{:0{}b} '.format(c.states[0][1] & (2**c.bits - 1), c.bits)
                else:
                    state = c.states[0][1]

                ident = _vcd_identifiers[i]
                prev_states[i] = state

                fh.write('{}{}\n'.format(state, ident))

            if init_with_dumpvars:
                fh.write('$end\n')


            # Dump changes
            es_channels = {}
            for i, c in enumerate(self.channels):
                es_channels[i] = iter(c.states) #decode.EdgeSequence(iter(v.states), self.timescale)

            es = decode.MultiEdgeSequence(es_channels, self.timescale)

            while not es.at_end():
                es.advance_to_edge()
                es.advance()

                # Determine which channels changed
                cur_states = {}
                for i in xrange(len(es_channels)):
                    ident = _vcd_identifiers[i]
                    cur_states[i] = es.cur_state(i)

                changed = []
                for i in cur_states.iterkeys():
                    #ident = _vcd_identifiers[i]
                    if cur_states[i] != prev_states[i]:
                        changed.append(i)

                if len(changed) > 0:
                    timestamp = int((es.cur_time() + self.timescale / 1000) / self.timescale) - 1
                    #print('## gen timestamp:', es.cur_time(), self.timescale, timestamp, int(es.cur_time() / self.timescale))
                    fh.write('#{}\n'.format(timestamp))
                    #print('## changed:', changed, [_vcd_identifiers[i] for i in changed])
                    for i in changed:
                        c = self.channels[i]
                        ident = _vcd_identifiers[i]

                        if c.bits > 1:
                            state = 'b{:0{}b} '.format(cur_states[i] & (2**c.bits - 1), c.bits)
                        else:
                            state = cur_states[i]

                        fh.write('{}{}\n'.format(state, ident))

                prev_states = cur_states


            


