================
Installing Ripyl
================

The Ripyl library will work on all platforms that support a Python interpreter. The following is a brief guide to installing the ripyl library. You will generally need administrative or super user (root) access to perform the installation as indicated below.

Dependencies
------------

Ripyl requires the following:
    * `python <http://www.python.org/>`_ 2.7 or 3.x
    * `scipy <http://www.scipy.org/>`_ >= 0.11.0 (also requires `numpy <http://www.numpy.org/>`_)

Optional libraries are:
    * `matplotlib <http://matplotlib.org/>`_ for plotting support
    * `cython <http://cython.org/>`_ >= 0.17 for improved performance

You should ensure the dependencies are installed and functioning properly on your platform before attempting to install Ripyl.

Installation
------------

Download the compressed source archive for your platform and extract its contents. On all platforms you can install from a command prompt. From an administrative or root shell type the following command from the directory containing the decompressed archive.

.. code-block:: sh

  > python setup.py install

This will install a copy of Ripyl library to the Python site-packages or dist-packages directory and enable the ``ripyl_demo`` script.

On some Unix platforms you may need to install to your home directory or use root access through sudo.

.. code-block:: sh

  > python setup.py install --home=~


.. code-block:: sh

  > sudo python setup.py install
  [sudo] password for user: *****


On Windows you can optionally run the executable installer to setup Ripyl.

Cython
------

The Ripyl library has been designed with optional Cython support. By default the installation script will detect and enable Cython if it is present. You can force Cython support off by passing the ``--without-cython`` argument to setup.py.

Testing
-------

You can run the Ripyl library test suite using the enhanced ``unittest`` from Python 2.7 or greater. All tests are run from the base directory of the source distribution (where setup.py is located)

.. code-block:: sh

  > python -m unittest discover
  
This will find the test suites in the ``test`` directory and run them.
