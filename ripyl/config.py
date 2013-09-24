#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Manage Ripyl configuration data
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

import ConfigParser
import os


use_cython = False
cython_prebuild = False
cython_active = False

def _parse_config():
    '''Read the library configuration file if it exists'''

    default_setup = {
        'use_cython': 'False',
        'cython_prebuild': 'False'
    }

    config = ConfigParser.ConfigParser(default_setup)
    ripyl_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(ripyl_dir, 'ripyl.cfg')
    config.read(config_path)

    if 'setup' in config.sections():
        global use_cython
        global cython_prebuild
        use_cython = config.getboolean('setup', 'use_cython')
        cython_prebuild = config.getboolean('setup', 'cython_prebuild')

_parse_config()


def write_config(cfg_path, use_cython, cython_prebuild):
    '''Write a file for the Ripyl build configuration'''
    config = ConfigParser.ConfigParser()
    config.add_section('setup')
    config.set('setup', 'use_cython', str(use_cython))
    config.set('setup', 'cython_prebuild', str(cython_prebuild))

    with open(cfg_path, 'wb') as fh:
        config.write(fh)





