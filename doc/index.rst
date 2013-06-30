.. Ripyl documentation master file, created by
   sphinx-quickstart on Tue Mar 12 17:53:08 2013.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Ripyl library documentation
===========================

Ripyl is a library for decoding serialized data collected from an oscilloscope
or logic analyzer. It supports a variety of protocols and can be readily extended
with new protocols.

It can process a waveform like this:

.. image:: image/uart_plain.png

... and produce an annotated result like this:

.. image:: image/uart_hello_small.png

Features include:
    * Multi-protocol support:
        ==== === ======== ==========
        HSIC I2C ISO 9141 ISO 14230
        PS/2 SPI UART     USB 2.0  
        ==== === ======== ==========
    * Protocol simulation
    * Annotated plotting

Getting started
===============

If you are new to Ripyl you can get started by reviewing the :doc:`introductory guide <intro>` and following the :doc:`tutorial <rst/tutorial>`.


Contents
========

.. toctree::
   :maxdepth: 2

   rst/installation
   rst/intro
   rst/tutorial
   rst/protocols
   api_reference
   apidoc/modules


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

