======================
Common data structures
======================

The Ripyl library makes use of a few common data structures that will be discussed below.

.. _streams:

Streams
-------

Throughout the Ripyl documentation there is reference to "streams" of data. This is a term used to describe an informally defined sequence of sample or edge data that is used as input and output of many library functions. A stream consists of a sequence (list, tuple, etc.) or iterable (iterator or generator function object) that contains/yields a series of tuple pairs of numbers. The first number is always a float representing the time that the second element of the pair occurs at. The second number is either a float or an int that represents a sample or logical edge state (high, low, middle, etc.) respectively. The former case is referred to as a "sample stream" the latter is an "edge stream".

The time value in each pair is an arbitrary time in seconds relative to whatever point is desired. Negative values are acceptable. The only firm requirement is that time increases monotonically. For sample streams the interval between successive time values should be fixed before applying certain signal processing operations like :func:`~.sigproc.filter_waveform` and :func:`~.sigproc.noisify`. Otherwise, a variable sample rate will be handled appropriately.

Sample streams are farily self explanatory. They are a time series of sampled data points. Edge streams are different in that they represent the logical levels of edge transitions. The time intervals between edges are not fixed. The logical state of each edge represents a transition at the current time that is maintained until the next edge in the sequence. Logical states are encoded as an integer value. For waveforms with binary states these will be 0 for low and 1 for high. For differential signals the states are -1 for low, 0 for differential-0, and 1 for high. The first element of an edge stream establishes the initial state of the stream and does not represent an edge. Internally all of the decode functions convert their input streams to edge streams before proceding to decode their content.


StreamRecords
-------------

All of the base-level decode functions that operate on raw sampled data produce output in the form of an iterable yielding objects based on the :class:`~.streaming.StreamRecord` class. This allows for the simple implementation of higher level protocols that consume base-level decoder output and yield their own StreamRecord derived objects. The iterators producing StreamRecord objects are also referred to as "streams" in the documentation. The distinction between the these and the sample/edge streams is apparent from the context of processing that is respectively performed after or before decoding.

All StreamRecord objects have four main attributes: :py:attr:`~.streaming.StreamRecord.kind`, :attr:`~.streaming.StreamRecord.status`,
:attr:`~.streaming.StreamRecord.subrecords`, and :attr:`~.streaming.StreamRecord.stream_id`.

The ``kind`` attribute is a string that provides a way to identify different types of StreamRecord objects. This allows a protocol to return different 'kinds' of data without necessarily creating different sub-classes for each one.

The ``status`` attribute is an integer code representing the general status of the decode process for each StreamRecord. This provides a way to report errors without interrupting subsequent processing. The baseline status codes are defined in the enumeration :class:`ripyl.streaming.StreamStatus`. The default success code is "Ok" which is 0. Any status code above "Warning" (100) is a warning and any code above "Error" (200) is an error. Additional status codes may be defined by each protocol.

The ``subrecords`` attribute is a list of additional StreamRecord objects that are the children of the current object. They are used by various decoders to create a heirarchy of decoded data at varying levels of detail. An example case is the :mod:`UART <.protocol.uart>` decoder that yields StreamRecords for each decoded byte each of which has subrecords with details on the start bit, parity bit, and stop bit locations.

The ``stream_id`` attribute is largely unused in the current implementation of Ripyl. It is intended to allow separate streams of decoded data to be present in a single iterator. Each stream is assigned a different ID number that can be checked later to isolate data from different streams. The :func:`~.streaming.merge_streams` function combines two separate StreamRecord streams and assigns new IDs to each one. There is no practical use for this behavior as yet, though.

StreamRecord objects have a :meth:`~.streaming.StreamRecord.nested_status` method that returns the largest status code for the current StreamRecord and all of its children. This can be useful when an error code is present in a subrecord but not in the containing StreamRecord.

StreamRecord subclasses
~~~~~~~~~~~~~~~~~~~~~~~

There are two main sub-classes of StreamRecord: :class:`~.streaming.StreamSegment` and :class:`~.streaming.StreamEvent`. The former represents information extracted from a span of time in the input stream. The latter represents events that happen at a specific point in time. StreamSegments can overlap in time. The children of a StreamSegment will typically be other StreamSegment objects that have a time span contained within the bounds of their parent but this is not rigidly enforced by the Ripyl library.

StreamSegment and StreamEvent add a ``data`` attribute to the base StreamRecord. This is the location of any decoded data represented by the object. Its type is dependent on the decoder. Some decoders store a plain integer representing a decoded byte or word. Other decoders will put more complex objects into the ``data`` attribute thus using the StreamSegment as a wrapper for insertion into the output stream. The attribute may be None if there is nothing useful to be stored.

StreamSegment objects have ``start_time`` and ``end_time`` attributes representing the span of time they cover. StreamEvent objects have a ``time`` attribute to identify the time of their event.

Each protocol decoder has its own system for representing decoded data in the StreamRecord-based objects. They generally sub-class StreamSegment and may have additional methods and attributes added to the base object. In addition to any sub-classing, StreamRecord objects can always be differentiated by their ``kind`` attributes.


Iterators
---------

Many of the functions in Ripyl are `generator functions <http://docs.python.org/2/howto/functional.html#generators>`_ that yield results through an iterable generator object rather than returning a result all at once. Some functions require an iterator as input and will not work properly if a list is passed instead. The following examples show how to convert between lists and iterators as needed.

It is important to realize that generator objects result in lazy evaluation and that the function call to them does not terminate until they have no more data to produce. You can force evaluation with the list() built-in.

.. code-block:: python

    # Decode function produces an iterable generator object
    records_it = XXX.XXX_decode()

    # The decode operation has *not* been performed yet

    records = list(records_it)
    # The list() built-in consumes the iterator and forces execution of XXX_decode()


Note that iterators can only advance through a sequence and once completed they can not be reiterated again. If you need to feed the data from a consumed iterator back into a function you should save it as a list object and then use iter() to create a fresh iterator over that list.


.. code-block:: python

    # The SPI simulator produces three edge stream iterators in a tuple
    clk_it, data_io_it, cs_it = spi.spi_synth(...)

    # Convert the edge stream to a sample stream
    clk_ss_it = sigproc.synth_wave(clk_it, sample_rate, rise_time)

    # clk_it can no longer be used by another function as it is being consumed by synth_wave()

    # Consume the sample iterator
    clk_samples = list(clk_ss_it)

    # clk_ss_it can no longer be used by another function

    # Create a new iterator on clk_samples using iter()
    records_it = spi.spi_decode(iter(clk_samples), ...)


You can also use the built-in `itertools.tee() <http://docs.python.org/2/library/itertools.html#itertools.tee>`_ function to split an iterator into two or more iterators if you need to process a stream data set more than once.

.. code-block:: python

    import itertools
    ...

    # Tee the sample iterator (nothing consumed yet)
    clk_samples, clk_ss_it = itertools.tee(clk_ss_it)

    # clk_ss_it has been reassigned to a new iterator and clk_samples
    # is now also an iterator

    # We can use clk_samples directly now. clk_samples is consumed here
    records_it = spi.spi_decode(clk_samples, ...)

    # clk_ss_it is still iterable after clk_samples has been consumed
    for t,s in clk_ss_it:
        pass

The functions in the :mod:`.sigproc` module have been designed to take an iterable stream as input and yield a stream as output. This allows them to be chained without generating intermediate lists of data.

.. code-block:: python

    import ripyl.sigproc as sp
    ...

    clk_ss_it = sp.synth_wave(clk_it, sample_rate, rise_time)
    clk_ss_it = sp.amplify(clk_ss_it, gain=10.0, offset=5.0)
    clk_ss_it = sp.noisify(clk_ss_it, snr_db=20.0)
    clk_ss_it = sp.quantize(clk_ss_it, full_scale=10.0)
    # No proecssing performed up to this point

    # Consume iterator and perform all previous operations
    clk_samples = list(clk_ss_it)

An operation chain can also be performed as nested function calls. This becomes impractical, however, for more than a couple operations.
    
.. code-block:: python

    import ripyl.sigproc as sp
    ...

    clk_ss_it = sp.quantize(sp.noisify(sp.amplify(sp.synth_wave(clk_it, sample_rate, rise_time), gain=10.0, offset=5.0), snr_db=20.0), full_scale=10.0)

    # Consume iterator and perform all previous operations
    clk_samples = list(clk_ss_it)



