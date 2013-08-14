#!/usr/bin/python
'''Script for running unittest discovery with an XMLTestRunner for reporting
This is the equivalent of running: python -m unittest discover
'''

import xmlrunner

__unittest = True

from unittest.main import main, TestProgram, USAGE_AS_MAIN
TestProgram.USAGE = USAGE_AS_MAIN

main(module=None, argv=['foo', 'discover'], testRunner=xmlrunner.XMLTestRunner(output='test/test-reports')) 
