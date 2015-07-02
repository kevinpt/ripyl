
from __future__ import print_function

import distribute_setup
distribute_setup.use_setuptools()

from setuptools import setup, Extension, Feature
import sys
import os
import fnmatch
import string
import numpy

# use README.rst for the long description
with open('README.rst') as fh:
    long_description = fh.read()
    
# scan the script for the version string
version_file = 'ripyl/__init__.py'
version = None
with open(version_file) as fh:
    try:
        version = [line.split('=')[1].strip().strip("'") for line in fh if line.startswith('__version__')][0]
    except IndexError:
        pass

if version is None:
    raise RuntimeError('Unable to find version string in file: {0}'.format(version_file))


cython_exists = False
cmdclass = {}

try:
    from Cython.Distutils import build_ext
    from Cython.Compiler.Version import version as cy_version
    from pkg_resources import parse_version

    # Check cython version
    min_cy_version = '0.17'
    if parse_version(cy_version) < parse_version(min_cy_version):
        print('Older Cython version {} found. Need at least {}.'.format(cy_version, min_cy_version))
    else:
        print('Cython version {} found. Build enabled.'.format(cy_version))
        cython_exists = True
        cmdclass = {'build_ext': build_ext }
except ImportError:
    pass

use_cython = False if '--without-cython' in sys.argv else True
cython_prebuild = False


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
    cy_root = os.getcwd()
    cy_files = [os.path.splitext(fn)[0] for fn in find_files('*.pyx', cy_root)]
    #print('### cy_files:', cy_files)

    # Convert slashes to dotted module notation
    trans = string.maketrans('/\\', '..')
    cy_modules = [f.translate(trans) for f in cy_files]
    
    # Remove the leading porton of the paths up to "cython"
    cy_modules = ['.'.join(m[m.find('cython'):].split('.')[1:]) for m in cy_modules]

    return cy_modules



features = {}
#if 'install' in sys.argv or 'build' in sys.argv or 'build_ext' in sys.argv:
if cython_exists:
    #import ripyl.config as config

    # Find all cython modules
    cy_module_names = find_cy_modules()

    ext_modules = []
    cy_root = ['ripyl', 'cython']
    for mname in cy_module_names:
        full_mname = '.'.join([e for x in [cy_root, [mname]] for e in x])
        #mfile = '{}.pyx'.format(os.path.join(*[e for x in [cy_root, mname.split('.')] for e in x]))
        mfile = '{}.pyx'.format(os.path.join(*full_mname.split('.')))
        #print '### create extension', mname, full_name, mfile
        ext_modules.append(Extension(full_mname, [mfile], extra_compile_args=['-O3']))

    cython_prebuild = True if use_cython else False
    features = {
        'cython': Feature('Optional Cython modules', standard=True, ext_modules=ext_modules)
    }

#print '$$$ use_cython', use_cython, cython_prebuild

#if 'install' in sys.argv:
#    write_config(os.path.join('ripyl', 'ripyl.cfg'), use_cython, cython_prebuild)


# Subclass build_py command to add our own hook to write a config file
from setuptools.command.build_py import build_py as _build_py

class build_py(_build_py):
    #user_options = _build_py.user_options
    #boolean_options = _build_py.boolean_options

    def initialize_options(self):
        _build_py.initialize_options(self)

    def finalize_options(self):
        _build_py.finalize_options(self)

    def run(self):
        cfg_path = os.path.join(self.build_lib, 'ripyl', 'ripyl.cfg')
        #print('$$$$ mkpath:', os.path.dirname(cfg_path))
        self.mkpath(os.path.dirname(cfg_path))
        print('Writing Ripyl configuration file: {}'.format(cfg_path))
        self.write_config(cfg_path, use_cython, cython_prebuild)

        # Read back the config file for verification
        with open(cfg_path, 'r') as f:
            for line in f:
                print('  >', line.rstrip())

        # Write additional config file into source directory to support
        # in place testing from Jenkins.
        #self.write_config(os.path.join('ripyl', 'ripyl.cfg'), use_cython, cython_prebuild)

        return _build_py.run(self)

    #def get_module_outfile(self, build_dir, package, module):
        #print('$$$$ get outfile:', build_dir, package, module)
        #return _build_py.get_module_outfile(self, build_dir, package, module)

    def write_config(self, cfg_path, use_cython, cython_prebuild):
        if sys.hexversion < 0x3000000:
            import ConfigParser as cp
        else:
            import configparser as cp

        config = cp.ConfigParser()
        config.add_section('setup')
        config.set('setup', 'use_cython', str(use_cython))
        config.set('setup', 'cython_prebuild', str(cython_prebuild))

        with open(cfg_path, 'w') as fh:
            config.write(fh)

cmdclass['build_py'] = build_py



setup(name='ripyl',
    version=version,
    author='Kevin Thibedeau',
    author_email='kevin.thibedeau@gmail.com',
    url='http://code.google.com/p/ripyl/',
    download_url='https://drive.google.com/folderview?id=0B5jin2146-EXV0h6eW5RNDJvUm8&usp=sharing',
    description='A library for decoding serial data captured from oscilloscopes and logic analyzers',
    long_description=long_description,
    install_requires = ['scipy >= 0.11.0', 'numpy >= 1.7.0'],
    packages = ['ripyl', 'ripyl.protocol', 'ripyl.protocol.infrared', 'ripyl.util', 'ripyl.cython'],
    py_modules = ['ripyl_demo'],
    cmdclass = cmdclass,
    #ext_modules = extensions,
    features = features,
    entry_points = {
        'console_scripts': ['ripyl_demo = ripyl_demo:main']
    },

    include_package_data = True,
    package_data = {
        '': ['*.cfg']
    },
    include_dirs = [numpy.get_include()],

    use_2to3 = True,
    test_suite = 'test',
    
    keywords='serial decode oscilloscope logic analyzer',
    license='LGPLv3',
    classifiers=['Development Status :: 5 - Production/Stable',
        'Operating System :: OS Independent',
        'Intended Audience :: Science/Research',
        'Natural Language :: English',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)',
        'Topic :: Scientific/Engineering :: Information Analysis',
        'Topic :: Software Development :: Libraries :: Python Modules'
        ]

    )
