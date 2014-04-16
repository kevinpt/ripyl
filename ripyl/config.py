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
    '''Represent a monkeypatch object

    This class provides a means to track and control pairs of class and function objects
    that can be swapped at will. This allows simplified monkeypatching for replacing
    python code with Cython equivalents.
    '''
    def __init__(self, py_mname, obj_name, obj, orig_obj):
        '''
        py_mname (string)
            The name of the module containing the original python object in dotted notation

        obj_name (string)
            The name of the object to be patched

        obj (function or class object)
            Reference to the replacement object patched over the original

        orig_obj (function or class object)
            Reference to the original object

        '''
        self.py_mname = py_mname
        self.obj_name = obj_name
        self.obj = obj
        self.orig_obj = orig_obj
        self.active = False


    def activate(self):
        '''Apply the monkeypatch over the orignal object'''
        if not self.active:
            sys.modules[self.py_mname].__dict__[self.obj_name] = self.obj
            self.active = True

    def revert(self):
        '''Restore the original object is it was previously monkeypatched'''
        if self.active:
            sys.modules[self.py_mname].__dict__[self.obj_name] = self.orig_obj
            self.active = False


class ConfigSettings(object):
    '''Container for general ripyl library settings'''
    def __init__(self):
        self.use_cython = False       # Indicates Cython should be used
        self.cython_prebuild = False  # Tracks whether Cython code was compiled during library installation
        self.python_fallback = True   # Silently ignore any failed cython import
        self.patched_objs = []        # List of PatchObject to control monkeypatching
        self.config_source = 'unknown'
        self.dbg_config_path = 'unknown'

    @property
    def cython_active(self):
        '''Identify if Cython modules have been monkeypatched

        Returns True if any patches have been applied'''
        return any(po.active for po in self.patched_objs)

    @cython_active.setter
    def cython_active(self, value):
        for po in self.patched_objs:
            if value:
                po.activate()
            else:
                po.revert()


    def find_patch_obj(self, obj_path):
        '''Search for a PatchObject by name

        obj_path (string)
            Full path to the object in dotted notation (ex: 'ripyl.module.object')

        Returns a PatchObject if found or None.
        '''
        try:
            py_mname, obj_name = obj_path.rsplit('.', 1)
        except ValueError:
            return None

        for po in self.patched_objs:
            if po.py_mname == py_mname and po.obj_name == obj_name:
                return po

        return None


def _parse_config():
    '''Read the library configuration file if it exists'''
    global settings

    default_setup = {
        'use_cython': 'False',
        'cython_prebuild': 'False'
    }

    config = ConfigParser.ConfigParser(default_setup)
    ripyl_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(ripyl_dir, 'ripyl.cfg')
    config.read(config_path)

    settings.config_path = config_path

    if 'setup' in config.sections():
        settings.use_cython = config.getboolean('setup', 'use_cython')
        settings.cython_prebuild = config.getboolean('setup', 'cython_prebuild')
        settings.config_source = config_path


def write_config(cfg_path, use_cython, cython_prebuild):
    '''Write a file for the Ripyl build configuration'''
    config = ConfigParser.ConfigParser()
    config.add_section('setup')
    config.set('setup', 'use_cython', str(settings.use_cython))
    config.set('setup', 'cython_prebuild', str(settings.cython_prebuild))

    with open(cfg_path, 'wb') as fh:
        config.write(fh)


# Parse settings when this module loads

settings = ConfigSettings()
_parse_config()

# Check environment for variables that effect configuration
ripyl_cython_env = os.getenv('RIPYL_CYTHON')

if ripyl_cython_env is not None:
    ripyl_cython_env = ripyl_cython_env.lower() in ('1', 'true', 't', 'y', 'yes')

    settings.use_cython = ripyl_cython_env





