#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Enumeration support
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

class Enum(object):
    '''Base class for enumeration classes
    
    This provides a name() class method that will return the string
    attribute name for an encoded enumeration value.
    
    e.g.
    
    >>> class Colors(Enum):
    ...     blue = 1
    ...     red = 2
    ...     green = 3
        
    >>> Colors.name(Colors.red)
    'red'
    
    >>> Colors.name(1, full_name=True)
    'Colors.blue'

    "Instantiating" the Enum sub-class calls the name() method as well:
    
    >>> Colors(3, full_name=False)
    'green'
    
    If necesssary you can use non-integers as the values as long as they are hashable:
    
    >>> class MathConst(Enum):
    ...     pi = 3.2     # in certain US states :)
    ...     e = 2.71828
        
    >>> MathConst.pi
    3.2
    
    '''

    @classmethod
    def name(cls, value, full_name=False):
        '''Lookup the enumeration name with the provided value

        value (hashable)
            A hashable Enum value (typically int) to find a name for.

        full_name (bool)
            Include full name of Enum object in result

        Returns a string for the Enum attribute associated with value.
        '''
        
        try:
            enum_lookup = cls._enum_lookup
        except AttributeError:
            # Build inverse dict of class attributes with their values as key
            enum_lookup = dict((v, k) for k, v in cls.__dict__.items() if k[0] != '_')
            cls._enum_lookup = enum_lookup
        
        try:
            aname = enum_lookup[value]
            prefix = cls.__name__ + '.' if full_name else ''
            return prefix + aname

        except KeyError:
            return 'unknown'

    def __new__(cls, value, full_name=False):
        '''Override class instantitation to perform name lookup instead'''
        return cls.name(value, full_name)
