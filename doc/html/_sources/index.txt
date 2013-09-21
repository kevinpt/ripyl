.. Ripyl documentation master file, created by
   sphinx-quickstart on Tue Mar 12 17:53:08 2013.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Ripyl library documentation
===========================

Ripyl is a library for decoding serialized data collected from an oscilloscope
or logic analyzer. It supports a variety of protocols and can be readily extended
with new protocols. Ripyl is useful for offline decoding of data collected on
instruments with no built in support for decoding or lacking support for more
advanced protocols.

It can process a waveform like this:

.. image:: image/uart_plain.png

... and produce an annotated result like this:

.. image:: image/uart_hello_small.png

The library provides decoded information in an easily traversed tree detailing the time and data for each sub-element of a protocol transmission.

Features include:
    * Multi-protocol support:
        ================== ================ ======================= ========================
        :ref:`HSIC <hsic>` :ref:`I2C <i2c>` :ref:`ISO 9141 <kline>` :ref:`ISO 14230 <kline>`
        :ref:`PS/2 <ps2>`  :ref:`SPI <spi>` :ref:`UART <uart>`      :ref:`USB 2.0 <usb>`
        :ref:`RC5 <rc5>`   :ref:`RC6 <rc6>` :ref:`NEC <nec>`        :ref:`SIRC <sirc>`
        ================== ================ ======================= ========================
    * Protocol simulation
    * Annotated plotting
    * Layering of protocols
    * Automated parameter analysis (logic levels, baud rate)

Getting started
===============

If you are new to Ripyl you can get started by reviewing the :doc:`introductory guide <rst/intro>` and following the :doc:`tutorial <rst/tutorial>`.


Contents
========

.. toctree::
   :maxdepth: 2

   rst/installation
   rst/intro
   rst/tutorial
   rst/reading_data
   rst/data_structures
   rst/protocols
   apidoc/modules


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

