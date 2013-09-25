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
import sys


class PatchObject(object):
    def __init__(self, py_mname, obj_name, obj, orig_obj):
        self.py_mname = py_mname
        self.obj_name = obj_name
        self.obj = obj
        self.orig_obj = orig_obj
        self.active = False

    def activate(self):
        if not self.active:
            sys.modules[self.py_mname].__dict__[self.obj_name] = self.obj
            self.active = True

    def revert(self):
        if self.active:
            sys.modules[self.py_mname].__dict__[self.obj_name] = self.orig_obj
            self.active = False

class ConfigSettings(object):
    def __init__(self):
        self.use_cython = False
        self.cython_prebuild = False
        self.patched_objs = []

    @property
    def cython_active(self):
        return any(po.active for po in self.patched_objs)

    def find_patch_obj(self, py_mname, obj_name):
        for po in self.patched_objs:
            if po.py_mname == py_mname and po.obj_name == obj_name:
                return po

        return None

settings = ConfigSettings()

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
        global settings
        settings.use_cython = config.getboolean('setup', 'use_cython')
        settings.cython_prebuild = config.getboolean('setup', 'cython_prebuild')

_parse_config()


def write_config(cfg_path, use_cython, cython_prebuild):
    '''Write a file for the Ripyl build configuration'''
    config = ConfigParser.ConfigParser()
    config.add_section('setup')
    config.set('setup', 'use_cython', str(settings.use_cython))
    config.set('setup', 'cython_prebuild', str(settings.cython_prebuild))

    with open(cfg_path, 'wb') as fh:
        config.write(fh)





