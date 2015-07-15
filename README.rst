.. image:: http://kevinpt.github.io/ripyl/_static/Ripyl_logo_100px.png

=============================
Ripyl protocol decode library
=============================


Ripyl is a library for decoding serialized data collected from an oscilloscope
or logic analyzer. It supports a variety of protocols and can be readily
extended with new protocols. Ripyl is useful for offline decoding of data
collected on instruments with no built in support for decoding or lacking
support for more advanced protocols.

It can process a waveform like this:

.. image:: http://kevinpt.github.io/ripyl/_images/uart_plain.png

... and produce an annotated result like this:

.. image:: http://kevinpt.github.io/ripyl/_images/uart_hello_small.png

Using Ripyl is as simple as follows:

.. code-block:: python

  import ripyl
  import ripyl.protocol.uart as uart

  raw_samples, sample_period = read_samples_from_your_oscilloscope()
  txd = ripyl.streaming.samples_to_sample_stream(raw_samples, sample_period)
  records = list(uart.uart_decode(txd, bits=8, parity='even', stop_bits=1))

The library provides decoded information in an easily traversed tree detailing the time and data for each sub-element of a protocol transmission.

Take a look at the `online documentation <http://kevinpt.github.io/ripyl/>`_ for more information on Ripyl's capabilites.

Requirements
------------
* Python 2.7 or 3.x
* SciPy >= 0.11.0
* Numpy >= 1.7.0

Optional libraries
------------------
* Matplotlib for plotting support
* Cython >= 0.17 for improved performance


Features
--------
* Multi-protocol support:
    ======== ========= ==== ===
    CAN      HSIC      I2C  LIN
    ISO 9141 ISO 14230 NEC  PS/2
    RC5      RC6       SIRC SPI
    UART     USB 2.0
    ======== ========= ==== ===
* Protocol simulation
* Annotated plotting
* Layering of protocols
* Automated parameter analysis (logic levels, baud rate)

Download
--------
You can access the Ripyl Git repository from `Github
<https://github.com/kevinpt/ripyl>`_. `Packaged source code <https://drive.google.com/folderview?id=0B5jin2146-EXV0h6eW5RNDJvUm8&usp=sharing>`_
is also available for download.

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

Cython
------
The Ripyl library has been designed with optional Cython support. By default
the installation script will detect and enable Cython if it is present. You
can force Cython support off by passing the ``--without-cython`` argument to
setup.py. The status of the Cython configuration is written into a ripyl.cfg
file at build time. You can enable or disable the use of Cython after Ripyl
is installed by setting the `RIPYL_CYTHON` environment variable to a true or
false value as desired:

  ``> export RIPYL_CYTHON=1``

Licensing
---------
This library is open sourced under the LGPL 3 license.
See LICENSE.txt for the full license.

