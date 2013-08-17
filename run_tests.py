#!/usr/bin/python
'''Script for running unittest discovery with an XMLTestRunner for reporting
This is the equivalent of running: python -m unittest discover
'''

import xmlrunner
from optparse import OptionParser

__unittest = True

from unittest.main import main, TestProgram, USAGE_AS_MAIN
TestProgram.USAGE = USAGE_AS_MAIN


parser = OptionParser()
parser.add_option('-x', '--xml-report', dest='xml_report', action='store_true', default=False, help='enable XMLTestRunner')

options, args = parser.parse_args()

if options.xml_report:
    test_runner = xmlrunner.XMLTestRunner(output='test/test-reports')
    print 'Running tests with XMLTestRunner'
else:
    test_runner = None


main(module=None, argv=['foo', 'discover'], testRunner=test_runner) 
