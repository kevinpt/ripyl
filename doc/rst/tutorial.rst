==============
Ripyl tutorial
==============

This tutorial provides an introduction to the use of the Ripyl library. It shows you how to do the following:

* :ref:`Prepare your data for processing <prepare-data>`
* :ref:`Perform the decode operation <decode-data>`
* :ref:`Analyze the results <analyze-results>`
* :ref:`Deal with problems <problems>`


.. _prepare-data:

Prepare your data
-----------------

Getting your sampled data ready for use by Ripyl is the most significant hurdle you will face. The Ripyl library needs to work on a sequence of samples or edge transitions to perform its decode. In most cases you will have sampled data from an oscilloscope or a logic analyzer to process. It is beyond the scope of the Ripyl library to provide device specific support. You will have to figure out how to get the raw data from these devices into an array that can be passed to Ripyl. Many devices support some form of CSV output that can be processed with the `csv module <http://docs.python.org/2/library/csv.html>`_ from the Python standard library. If your device supports binary output, however, you will be able to read large data sets more rapidly.

Ripyl's processing is performed through a pipeline of `generator functions <http://docs.python.org/2/tutorial/classes.html#generators>`_ that minimize the amount of data passed around in arrays. To support this system, the raw samples have to be converted to a :ref:`sample stream <streams>`.

.. code-block:: python

    import ripyl
    import ripyl.sigproc as sigp
    import ripyl.protocol.uart as uart
    
    raw_samples, sample_period = read_samples_from_your_oscilloscope()
    txd = sigp.samples_to_sample_stream(raw_samples, sample_period)

.. note::
    You will need to figure out how to populate the raw_samples and sample_period variables on your own. read_samples_from_your_oscilloscope() is just a placeholder that does not exist in Ripyl. See the section on :doc:`reading data <reading_data>` for some examples for various devices.
    
The ``txd`` variable is an iterable object that will extract data from ``raw_samples`` as needed and yield a series of sample stream tuples with time markers for each sample. If you need accurate time correlation you can pass an additional ``start_time`` parameter to the :func:`~.sigproc.samples_to_sample_stream` function.

.. note::

    Some logic analyzers may store edge transitions rather than sampled data. You can either work to convert these data sets into periodic samples or convert them directly into an ``edge stream`` prior to decode.

.. _decode-data:

Decode your data
----------------

Once you have your data converted to one or more sample streams the hard part is over. Now you just have to pass the stream(s) to an appropriate decoder. In this case we've captured the TXD signal on an asynchronous serial port so we will use the :mod:`UART <.protocol.uart>` decoder. Most of the decoders are configurable with parameters that can alter the protocol. For the UART decoder we need to provide the number of bits, stop bits, type of parity, and polarity (idle high or low). The baud rate is optional since the UART decoder can determine this automatically provided there is enough data (typically at least 11 frames).

.. code-block:: python

    bits = 8 # Anything, not just restricted to the standard 5,6,7,8,9
    parity = 'even' # or 'odd' or None
    stop_bits = 1 # Can be 1, 1.5, 2 or any non-standard value greater than 0.5
    polarity = uart.UARTConfig.IdleHigh
    
    records_it = uart.uart_decode(txd, bits, parity, stop_bits, polarity)
    
    # At this point we have an iterator but the decode has not been completed
    
    records = list(records_it) # This consumes the iterator and completes the decode
    
.. _analyze-results:

Analyze the results
-------------------

At this point we should have a list of :class:`~.streaming.StreamRecord`-based objects with our decoded data. An exception will be thrown if the decode process could not be completed. Recoverable errors will be reported in the records with their ``status`` attributes.

There are two main sub-classes of StreamRecord: :class:`~.streaming.StreamSegment` and :class:`~.streaming.StreamEvent`. The former represents information extracted from a span of time in the input stream. The latter represents events that happen at a specific point in time. StreamSegments can overlap in time. The children of a StreamSegment will typically be other StreamSegment objects that have a time span contained within the bounds of their parent but this is not rigidly enforced by the Ripyl library.

Each protocol decoder has its own system for representing decoded data in the StreamRecord-based objects. They generally sub-class StreamSegment and may have additional methods and attributes added to the base object. In addition to any sub-classing, StreamRecord objects can be differentiated by their ``kind`` attribute which is a string identifying the type of record.

For the UART decoder we will receive a series of :class:`~.uart.UARTFrame` objects with the ``kind`` attribute set to ``'UART frame'``.

Validate the decoded records
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You should not blindly accept the decoded output from Ripyl as valid. Any number of errors could happen during the decode process which may corrupt subsequent operations. You should scan through the records to validate them.

Every :class:`~.streaming.StreamRecord` object has a ``status`` attribute that contains a numeric status code. The baseline status codes are defined in the enumeration :class:`ripyl.streaming.StreamStatus`. The default success code is "Ok" which is 0. Any status code above "Warning" (100) is a warning and any code above "Error" (200) is an error. Additional status codes may be defined by each protocol.

.. code-block:: python

    import ripyl.streaming as stream

    success = True
    for rec in records:
        if rec.nested_status() != stream.StreamStatus.Ok:
            success = False
            break # Note: you may want to do some error recovery rather than just aborting

            
If ``success`` remains True then you can proceed to work with the decoded data. Otherwise you will have to find out what type of error happened and what action to take.

Note that it is best to test for inequality against a status code to ensure you don't miss any protocol specific additions.

.. code-block:: python

    if rec.nested_status() != stream.StreamStatus.Ok:
        pass # Ok: catches anything other than normal Ok

    if rec.nested_status() < stream.StreamStatus.Warning:
        pass # Ok: catches all status codes less severe than Error or Warning

    if rec.nested_status() == stream.StreamStatus.Error:
        pass # Bad: will miss additional error codes greater than Error

It is generally best to access the ``status`` attribute indirectly with the :meth:`~.StreamRecord.nested_status` method as it ensures you will receive the highest status code for a StreamRecord and any children it may have.

Extract your data
~~~~~~~~~~~~~~~~~

The decoded data is stored in a variety of ways depending on the protocol. The format is typically the smallest unit of data that can be decoded in isolation. For most serial protocols these units are "frames" that represent a single word of data. In the case of USB, the smallest decodable unit is a packet which could convey up to 1024 bytes of data.

The decoded data is always stored in the ``data`` attribute of the StreamRecord objects (or a property aliased to ``data``). The type of object stored in the ``data`` attribute varies by protocol. For UART it is an integer representing each decoded word.

.. code-block:: python

    # Extract the data into a list
    data = [rec.data for rec in records]
    
    # If the data is ASCII text we can convert it to a list of lines
    lines = ''.join(chr(d) for d in data).split()

There may be additional information about each data frame contained within the subrecords attached to a StreamRecord object. This varies by protocol. In the case of UART there is a subrecord for the start bit, data bits, any parity bit if parity was enabled, and the stop bit(s). Each of these subrecords is a StreamSegment object that adds timing information to the base StreamRecord class. This allows us to identify precisely where each detected feature of a frame occured in time. They also have their own ``status`` attributes. If the parity subrecord is present, its status is used to flag a parity error rather than the top level status of the :class:`~.uart.UARTFrame` object it is a child of. This is why :meth:`~.StreamRecord.nested_status` should be called in most cases rather than just checking the top level ``status`` attribute.

Some protocols may insert non-data :class:`~.streaming.StreamEvent` objects to indicate additional information during the decode process. If this is the case the records should be filtered for only those that contain the desired data. For instance the :mod:`SPI <.spi>` decoder reports events for changes in chip select and the :mod:`I2C <.i2c>` decoder reports events for start, restart, and stop conditions. In the latter case these events serve as markers for the start and end of each bus transfer and may be useful for higher level decoders.

.. _problems:

What could go wrong?
--------------------

The protocol decoders perform some automatic parametric analysis to simplify the library interface. By default all decoders will attempt to perform automatic logic level analysis on the sample stream. The UART and USB decoders also provide automatic baud and bus speed detection. In some cases these automatic actions will fail or produce the wrong results.

Logic level detection
~~~~~~~~~~~~~~~~~~~~~

The protocol decoders need to do some statistical analysis of the sample stream(s) before they can start decoding. Internally each decoder works on an edge stream rather than directly on the sample stream. The samples need to be converted to edges by first discovering what the logic levels are, removing the need to manually specify logic thresholds. This requires consuming a portion of the input samples for analysis. By default the Ripyl library is limited to consuming 20000 samples for its logic level analysis. If the input has no identifiable edge transitions in this period the AutoLevelError exception will be raised. The analyzed samples are buffered and will still be used if they contain useful data for decode.

The logic level analysis may produce incorrect results if you have an unusual input signal that contains more than two identifiable logic levels (or three for differential USB). Consider the case of HighSpeed (480 Mb/s) USB devices where normal single-ended signaling levels are 0V and 0.4V but 3.3V may also be present during the initial connection phase and during any suspend period. This could interfere with the logic level detection process.

To remedy this problem you have two options. The simplest is to pass known logic levels to a decoder using the optional ``logic_levels`` parameter. This is a pair of floats (low, high) defining the upper and lower voltage levels of the signal. These levels should correspond to the actual high and low voltages of the waveform (ignoring unwanted peaks and noise) rather than the min and max input levels for the receiver (Vil and Vih).

.. code-block:: python

    logic = (0.0, 0.4) # Logic low and high for your signal
    records_it = XXX.XXX_decode(samples_it, ..., logic_levels=logic)

For protocols that use more than one sample stream, the logic level analysis is only performed on one stream. This is generally the one with the most activity such as a clock signal. It is assumed that the logic levels detected or specified for this stream are appropriate for all other streams fed to the decoder.

The other option is to manually generate an edge stream on a set of sampled data. This is a little more involved but offers more flexibility as you can set different logic levels for each sample stream and control the amount of hysteresis.

.. code-block:: python

    import ripyl
    import ripyl.sigproc as sigp
    from ripyl.decode import find_edges
    from ripyl.streaming import StreamType

    # Prepare your raw samples
    sample_stream = sigp.samples_to_sample_stream(raw_samples, sample_period)

    logic = (0.0, 0.4) # Logic low and high for your signal
    hysteresis = 0.4 # 40% of the transition band between low and high
    
    # Create an edge stream iterator
    edges_it = find_edges(sample_stream, logic, hysteresis)
    
    # Tell the decoder the input is an edge stream
    records_it = XXX.XXX_decode(edges_it, ..., stream_type = StreamType.Edges)


    
Baud and bus speed detection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    
The UART decoder provides automatic baud rate detection by default. It does this by analyzing the statistical distribution of time spans between edge transitions. This requires around 50 edges to be reliable. If insufficient edge transitions are present the AutoBaudError exception will be raised. If this happens you can either acquire new data with enough transitions or pass the proper baud rate to :func:`~.uart.uart_decode`. The UART decoder also coerces the detected baud rate to the nearest "standard" value from 110 to 921600. If your input has a non-standard baud rate you can disable this coercion with ``use_std_baud=False``.

The USB decoder uses the same detection logic to identify the different bus speeds used for USB devices. The minimum number of edges is 8 for USB speed detection rather than 50. This is sufficient to detect speed with just a single low-speed or full-speed handshake packet, the shortest packets used in the protocol. USB speed detection has been found to be reliable in all test cases and there is no provision for forcing the bus to a fixed speed in the decoder.
