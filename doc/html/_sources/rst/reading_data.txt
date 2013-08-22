=========================
Reading oscilloscope data
=========================

Ripyl does not provide any support for reading data formats directly produced by oscilloscopes and logic analyzers. A user of the library will have to take care of that independently before decoding with Ripyl. Most instruments will produce some form of CSV output that can be easily parsed with the `csv module <http://docs.python.org/2/library/csv.html>`_ in the Python standard library. There is no standard organization for CSV data so reading functions will be manufacturer and (possibly) model specific. Your instruments may also support other text based formats such as Matlab arrays that can be easily read by a Python script. If your device supports binary output, however, you will be able to read large data sets more rapidly.

Here are some example functions for reading data from various oscilloscopes.

LeCroy
------

Most LeCroy oscilloscopes support the same binary and CSV formats. Here is an example function for reading the CSV files produced by them.

.. code-block:: python

    import csv

    def read_lecroy_csv(fname):
        sample_period = 0.0
        raw_samples = []

        with open(fname, 'rb') as csvfile:
            c = csv.reader(csvfile)

            # Sample period is in cell B2 (1,1)
            # Time is in column D (3)
            # Samples are in column E (4)

            for row_num, row in enumerate(c):
                if row_num == 1: # get the sample period
                    sample_period = float(row[1])
                    break

            csvfile.seek(0)
            for row in c:
                raw_samples.append(float(row[4]))

        return raw_samples, sample_period
