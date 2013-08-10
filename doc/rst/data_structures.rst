======================
Common data structures
======================

The Ripyl library makes use of a few common data structures that will be discussed below.

Streams
-------

Throughout the Ripyl documentation there is reference to "streams" of data. This is a term used to describe an informally defined sequence of sample or edge data that is used as input and output of many library functions. A stream consists of a sequence (list, tuple, etc.) or iterable (iterator or generator function object) that contains/yields a series of tuple pairs of numbers. The first number is always a float representing the time that the second element of the pair occurs at. The second number is either a float or an int that represents a sample or logical edge state (high, low, middle, etc) respectively. The former case is referred to as a "sample stream" the latter is an "edge stream".

The time value in each pair is an arbitrary time in seconds relative to whatever point is desired. Negative values are acceptable. The only firm requirement is that time increases monotonically. For sample streams the interval between successive time values should be fixed before applying certain signal processing operations like filter_waveform() and noisify(). Otherwise, a variable sample rate will be handled appropriately.

Sample streams are farily self explanatory. They are a time series of sampled data points. Edge streams are different in that they represent the logical levels of edge transitions. The time intervals between edges are not fixed. The logical state of each edge represents a transition at the current time that is maintained until the next edge in the sequence. Logical states are encoded as an integer value. For waveforms with binary states these will be 0 for low and 1 for high. For differential signals the states are -1 for low, 0 for differential 0, and 1 for high. Internally all of the decode functions convert their input streams to edge streams before proceding to decode their content.


StreamRecords
-------------


Iterators
---------

Many of the functions in Ripyl are generator functions that yield results through an iterable generator object rather than returning a result all at once. Some functions require an iterator as input and will not work properly if a list is passed in instead.

.. code-block:: python

    # Decode function produces an iterable generator object
    records_it = XXX.XXX_decode()

    # The decode operation has *not* been performed yet

    records = list(records_it)
    # The list() built-in consumes the iterator and forces execution of the decode function


It is important to realize that generator objects result in lazy evaluation and that the function call to them does not terminate until they have no more data to produce. You can force evaluation with the list() built-in.

.. code-block:: python

    # The SPI simulator produces three edge stream iterators in a tuple
    clk, data_io, cs = spi.spi_synth(...)

    # Convert the edge stream to a sample stream
    clk_it = sigproc.synth_wave(clk, sample_rate, rise_time)

    # Consume the sample iterator
    clk_samples = list(clk_it)

    # clk_it can no longer be used by another function

    # Create a new iterator on clk_samples using iter()
    records_it = spi.spi_decode(iter(clk_samples), ...)

It is important to realize that iterators can only advance through a sequence and once completed they can not be reiterated again. If you need to feed the data from a consumed iterator back into a function you should save it as a list object and then use iter() to create a fresh iterator over that list.

    



