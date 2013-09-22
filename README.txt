=============================
Ripyl protocol decode library
=============================

Version: 1.0


Ripyl is a library for decoding serialized data collected from an oscilloscope
or logic analyzer. It supports a variety of protocols and can be readily
extended with new protocols. Ripyl is useful for offline decoding of data
collected on instruments with no built in support for decoding or lacking
support for more advanced protocols.

Dependencies
------------
* Python 2.7 or 3.x
* SciPy >= 0.11.0 (depends on numpy as well)

Optional libraries
------------------
* Matplotlib for plotting support
* Cython >= 0.19 for improved performance


Features
--------
* Multi-protocol support:
    ==== === ======== ==========
    HSIC I2C ISO 9141 ISO 14230
    PS/2 SPI UART     USB 2.0  
    RC5  RC6 NEC      SIRC
    ==== === ======== ==========
* Protocol simulation
* Annotated plotting
* Layering of protocols
* Automated parameter analysis (logic levels, baud rate)

Installation
------------
Download the compressed source archive for your platform and extract its
contents. On all platforms you can install from a command prompt. From an
administrative or root shell type the following command from the directory
containing the decompressed archive.

  ``> python setup.py install``

This will install a copy of Ripyl library to the Python site-packages or
dist-packages directory and enable the ``ripyl_demo`` script.

On some Unix platforms you may need to install to your home directory or use
root access through sudo.

  ``> python setup.py install --home=~``


  ``> sudo python setup.py install``
  ``[sudo] password for user: *****``


On Windows you can optionally run the executable installer to setup Ripyl.

Cython
------

The Ripyl library has been designed with optional Cython support. By default
the installation script will detect and enable Cython if it is present. You
can force Cython support off by passing the ``--without-cython`` argument to
setup.py.


Licensing
---------
This library is open sourced under the LGPL 3 license.
See LICENSE.txt for the full license.

