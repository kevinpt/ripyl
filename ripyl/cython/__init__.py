#!/usr/bin/python

'''Cython extension package'''

import ripyl

if ripyl.config.settings.cython_prebuild == False:
    #print 'No prebuild'
    import pyximport; pyximport.install()
#else:
    #print 'Using prebuild'

import inspect
import importlib
import sys
import os
import fnmatch
import string


def find_files(pattern, path):
    '''Recursively search for files that match a specified pattern'''
    result = []
    for root, dirs, files in os.walk(path):
        for name in files:
            if fnmatch.fnmatch(name, pattern):
                result.append(os.path.join(root, name))
    return result


def find_cy_modules():
    '''Find Cython modules

    Returns a list of Cython module names.
    '''
    # Strip extensions from module names
    cy_root = os.path.dirname(__file__)
    cy_files = [os.path.splitext(fn)[0] for fn in find_files('*.pyx', cy_root)]
    #print '### cy_files:', cy_files

    # Convert slashes to dotted module notation
    trans = string.maketrans('/\\', '..')
    cy_mods = [f.translate(trans) for f in cy_files]
    
    # Remove the leading porton of the paths up to "cython"
    cy_mods = ['.'.join(m[m.find('cython'):].split('.')[1:]) for m in cy_mods]

    return cy_mods


def monkeypatch_modules(modules, lib_base):
    '''Replace pure Python functions and classes with Cython equivalents

    modules (dict of modules)
        A dict of module objects keyed by their module name.

    lib_base (string)
        The base path of the library (ex: 'ripyl').

    Returns a list of PatchObject.
    '''
    patched_objs = []
    for mname, module in modules.iteritems():
        py_mname = '.'.join((lib_base, mname))
        if py_mname in sys.modules:
            objs = inspect.getmembers(module, inspect.isbuiltin)
            classes = inspect.getmembers(module, inspect.isclass)
            objs.extend(classes)
            # Monkeypatch the cython functions and classes over the original python implementation
            for obj_name, obj in objs:
                # Cython releases before 0.19.1 include extraneous internal classes in the extension modules.
                # We need to catch any attempts to access these classes that don't exist in the
                # Python implementations
                if obj_name in sys.modules[py_mname].__dict__:
                    orig_obj = sys.modules[py_mname].__dict__[obj_name]
                    po = ripyl.config.PatchObject(py_mname, obj_name, obj, orig_obj)
                    po.activate()
                    patched_objs.append(po)

    return patched_objs



# Find all cython modules
cy_module_names = find_cy_modules()

cy_modules = {}
for mname in cy_module_names:
    #print '##importing cython: "{}"'.format(mname)
    full_mname = 'ripyl.cython.' + mname
    try:
        cy_modules[mname] = importlib.import_module(full_mname)
    except ImportError, KeyError:
        msg = 'Could not import Cython module: {}'.format(full_mname)
        if ripyl.config.settings.python_fallback == True:
            print 'Error:', msg
        else:
            #print '@@@@@@@@@@ CYTHON ABORT'
            raise ImportError(msg)

#print 'cython modules:', cy_modules

ripyl.config.settings.patched_objs = monkeypatch_modules(cy_modules, 'ripyl')



