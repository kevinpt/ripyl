#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Test to determine minimum number of edges needed for auto-baud detection to work
'''

from __future__ import print_function, division

import numpy as np
import matplotlib.pyplot as plt

from data_synth import *
from decode import *

def to_sample_edges(edges, sample_rate):
    samples, levels = zip(*edges)
    ns = []
    for i, s in enumerate(samples):
        ns.append(int(s * sample_rate))
        
    return zip(ns, levels)

print('Generating random data sets')

data_sets = []
for i in xrange(10):
    rd = np.random.uniform(high=255.0, size=100).astype(int)
    cd = []
    for r in rd:
        cd.append(chr(r))
    data_sets.append(''.join(cd))

print('Generating edge sets')    
edge_sets = []
for ds in data_sets:
    edge_sets.append(to_sample_edges(serial_synth(ds), 10.0e6))

es_lens = []
for es in edge_sets:
    es_lens.append(len(es))

print('Shortest edge set:', min(es_lens))

baud_sets = []
for es in edge_sets:
    print('new set')
    bs = []
    for e in xrange(15,50):
        bs.append((e, find_symbol_rate(es[:e], 10.e6)))
    baud_sets.append(bs)
    

#print(baud_sets)  

for bs in baud_sets:
    ec, br = zip(*bs)
    #plt.hist(br)
    plt.plot(ec, br)
      
#plt.hist(es_lens)
plt.show()