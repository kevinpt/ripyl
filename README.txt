=============================
Ripyl protocol decode library
=============================

Version: 1.0


Ripyl is a library for decoding serialized data collected from an oscilloscope
or logic analyzer. It supports a variety of protocols and can be readily extended
with new protocols.

Dependencies
------------
* Python 2.7 or 3.x
* SciPy 0.11.0
* Optional: matplotlib for plotting waveforms with decoded results

Features
--------
* Decode multiple protocols (USB 2.0, UART, SPI, I2C)
* All protocols include a synthesis function for generating simulated waveforms.
* Automated parameter analysis (logic levels, baud rate)
* Supports layering of protocols
* Based on a pipeline of iterators that minimizes internal memory consumption

Installation
------------
For all platforms, installation via setup.py is provided. This uses the
Distribute fork of setuptools and will install Distribute if it is not already
present. After extracting the compressed archive, run the following command:

``> python setup.py install``

This will install the Ripyl distribution into your Python's site-packages.
An executable link will be created to the ripyl_demo script for exercising the
library.



Licensing
---------
This program is open sourced under the LGPL 3 license.
See LICENSE.txt for the full license.
