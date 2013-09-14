
import ripyl

if ripyl.config.cython_prebuild == False:
    print 'No prebuild'
    import pyximport; pyximport.install()
else:
    print 'Using prebuild'

import inspect
import importlib
import sys
import os
import fnmatch
import string


def find_files(pattern, path):
    ''''Recursively search for files that match a specified pattern'''
    result = []
    for root, dirs, files in os.walk(path):
        for name in files:
            if fnmatch.fnmatch(name, pattern):
                result.append(os.path.join(root, name))
    return result


def find_cy_modules():
    '''Find Cython modules'''
    # Strip extensions from module names
    cy_files = [os.path.splitext(fn)[0] for fn in find_files('*.pyx', '.')]

    # Convert slashes to dotted module notation
    trans = string.maketrans('/\\', '..')
    cy_modules = [f.translate(trans) for f in cy_files]
    
    # Remove the leading porton of the paths up to "cython"
    cy_modules = ['.'.join(m[m.find('cython'):].split('.')[1:]) for m in cy_modules]

    return cy_modules


def monkeypatch_modules(modules, lib_base):
    for mname, module in modules.iteritems():
        py_mname = '.'.join((lib_base, mname))
        if py_mname in sys.modules:
            objs = inspect.getmembers(module, inspect.isbuiltin)
            classes = inspect.getmembers(module, inspect.isclass)
            objs.extend(classes)
            # Monkeypatch the cython functions and classes over the original python implementation
            for obj_name, obj in objs:
                #print 'patching:', obj_name
                sys.modules[py_mname].__dict__[obj_name] = obj



# Find all cython modules
cy_module_names = find_cy_modules()

cy_modules = {}
for mname in cy_module_names:
    #print 'importing cython:', mname
    cy_modules[mname] = importlib.import_module('ripyl.cython.' + mname)

#print 'cython modules:', cy_modules

monkeypatch_modules(cy_modules, 'ripyl')


