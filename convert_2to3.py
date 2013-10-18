#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Jenkins helper script that runs 2to3 on local source if interpreter is Python 3

This should be run from a virtualenv based clone of the repository to avoid changing
2.7 code in a development area.
'''

from __future__ import print_function

import sys

if sys.version_info[0] == 2:
    print('Running Python 2: no changes made')
    sys.exit(0)

# We are running Python 3
# Convert source code

from subprocess import call

print('Running Python 3: converting source')
call('2to3 -w -n .', shell=True)
    
