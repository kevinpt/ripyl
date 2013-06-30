================
Installing Ripyl
================

The Ripyl library will work on all platforms that support a Python interpreter. The following is a brief guide to installing the ripyl library. You will generally need administrative or super user (root) access to perform the installation as indicated below.

Dependencies
------------

Ripyl requires the following:
    * `python <http://www.python.org/>`_ 2.7 or 3.x
    * `scipy <http://www.scipy.org/>`_ >= 0.11.0

For plotting support you can optionally install `matplotlib <http://matplotlib.org/>`_.

You should ensure the dependencies are installed and functioning properly on your platform before attempting to install Ripyl.

Installation
------------

Download the compressed source archive for your platform and extract its contents. On all platforms you can install from a command prompt. Type the following command from the directory containing the decompressed archive.

.. code-block:: sh

  > python setup.py install

This will install a copy of Ripyl library to the Python site-packages directory and enable the ``ripyl_demo`` script.

On Windows you can optionally run the executable installer to setup Ripyl.

Testing
-------

You can run the Ripyl library test suite using the enhanced ``unittest`` from Python 2.7 or greater. All tests are run from the base directory of the source distribution (where setup.py is located)

.. code-block:: sh

  > python -m unittest discover
  
This will find the test suites in the ``test`` directory and run them.
