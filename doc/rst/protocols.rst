===============
Ripyl protocols
===============

The Ripyl library supports a number of protocols for decoding. Protocol decoders can be layered on top of each other. This creates a distinction between base level decoders that operate on raw sample or edge data and higher level decoders that work with the results of a lower level decoder.

The base protocols provided with Ripyl are the following:

* :mod:`UART <.protocol.uart>`
* :mod:`I2C <.protocol.i2c>` (also handles SMBus)
* :mod:`SPI <.protocol.spi>`
* :mod:`PS/2 and AT keyboard <.protocol.ps2>`
* :mod:`USB 2.0 <.protocol.usb>` (all speeds and HSIC support)
* :mod:`ISO K-line <.protocol.iso_k_line>` (ISO 9141 and ISO 14230 automotive protocols)


All base level protocols in the library have functions to support the synthesis of arbitrary waveforms. This can be useful for testing or recreating special circumstances that would be challenging to perform with real hardware.

The higher level protocols provided with Ripyl are:

* :mod:`LM73 <.protocol.lm73>` temperature sensor (SMBus)
* :mod:`OBD-2 <.protocol.obd2>` automotive ECU message format


The protocol decoders do not check timing parameters to verify that they meet specifications. The emphasis is on getting usable data out of waveforms even if they depart from requirements.
