import distribute_setup
distribute_setup.use_setuptools()

from setuptools import setup, Extension, Feature
import sys
import os
import fnmatch
import string

# use README.txt for the long description
with open('README.txt') as fh:
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



try:
    from Cython.Distutils import build_ext
    cython_exists = True
except ImportError:
    cython_exists = False


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
    cy_root = os.path.dirname(__file__)
    cy_files = [os.path.splitext(fn)[0] for fn in find_files('*.pyx', cy_root)]
    #print '### cy_files:', cy_files

    # Convert slashes to dotted module notation
    trans = string.maketrans('/\\', '..')
    cy_modules = [f.translate(trans) for f in cy_files]
    
    # Remove the leading porton of the paths up to "cython"
    cy_modules = ['.'.join(m[m.find('cython'):].split('.')[1:]) for m in cy_modules]

    return cy_modules

def write_config(cfg_path, use_cython, cython_prebuild):
    import ConfigParser

    config = ConfigParser.ConfigParser()
    config.add_section('setup')
    config.set('setup', 'use_cython', str(use_cython))
    config.set('setup', 'cython_prebuild', str(cython_prebuild))

    with open(cfg_path, 'wb') as fh:
        config.write(fh)

ext_modules = []
features = {}
#if 'install' in sys.argv or 'build' in sys.argv or 'build_ext' in sys.argv:
if cython_exists:
    #import ripyl.config as config

    # Find all cython modules
    cy_module_names = find_cy_modules()

    cy_root = ['ripyl', 'cython']
    for mname in cy_module_names:
        full_mname = '.'.join([e for x in [cy_root, [mname]] for e in x])
        #mfile = '{}.pyx'.format(os.path.join(*[e for x in [cy_root, mname.split('.')] for e in x]))
        mfile = '{}.pyx'.format(os.path.join(*full_mname.split('.')))
        #print '### create extension', mname, full_name, mfile
        ext_modules.append(Extension(full_mname, [mfile]))

    cython_prebuild = True if use_cython else False
    features = {
        'cython': Feature('Optional Cython modules', standard=True, ext_modules=ext_modules)
    }

#print '$$$ use_cython', use_cython, cython_prebuild

if 'install' in sys.argv:
    write_config(os.path.join('ripyl', 'ripyl.cfg'), use_cython, cython_prebuild)



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
    cmdclass = {'build_ext': build_ext },
    #ext_modules = extensions,
    features = features,
    entry_points = {
        'console_scripts': ['ripyl_demo = ripyl_demo:main']
    },

    include_package_data = True,
    package_data = {
        '': ['*.cfg']
    },

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
