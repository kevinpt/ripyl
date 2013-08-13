import distribute_setup
distribute_setup.use_setuptools()

from setuptools import setup

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

setup(name='ripyl',
    version=version,
    author='Kevin Thibedeau',
    author_email='kevin.thibedeau@gmail.com',
    url='http://code.google.com/p/ripyl/',
    download_url='https://drive.google.com/folderview?id=0B5jin2146-EXV0h6eW5RNDJvUm8&usp=sharing',
    description='A library for decoding serial data captured from oscilloscopes and logic analyzers',
    long_description=long_description,
    install_requires = ['scipy >= 0.11.0', 'numpy >= 1.7.0'],
    packages = ['ripyl', 'ripyl.protocol', 'ripyl.util'],
    py_modules = ['ripyl_demo'],
    entry_points = {
        'console_scripts': ['ripyl_demo = ripyl_demo:main']
    },

    include_package_data = True,
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
