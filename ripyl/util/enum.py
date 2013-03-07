#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   Enumeration support
'''

# Copyright © 2013 Kevin Thibedeau

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
    
    >>> Colors.name(1, True)
    'Colors.blue'

    "Instantiating" the enum class calls the name() method as well:
    
    >>> Colors(3, True)
    'Colors.green'
    
    If necesssary you can use non-integers as the values as long as they are hashable:
    
    >>> class MathConst(Enum):
    ...     pi = 3.2     # in certain US states :)
    ...     e = 2.71828
        
    >>> MathConst.pi
    3.2
    
    '''

    @classmethod
    def name(cls, value, full_name=False):
        '''Lookup the enumeration name with the provided value'''
        
        try:
            enum_lookup = cls._enum_lookup
        except AttributeError:
            # Build inverse dict of class attributes with their values as key
            enum_lookup = dict((v,k) for k, v in cls.__dict__.items() if k[0] != '_')
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