#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Data synthesizer
'''

from __future__ import print_function, division
from optparse import OptionParser

import matplotlib.pyplot as plt
import matplotlib.patches as pts

import numpy as np

from collections import deque

from decode import *
from streaming import *
from sigproc import *
from protocol.spi import *
from protocol.uart import *
from protocol.i2c import *
from protocol.usb import *
from stats import OnlineStats


def read_bin_file(fname):
    import struct
    with open(fname, 'rb') as fo:
        sample_period = struct.unpack('<d', fo.read(8))[0]
        samples = []
        while True:
            s = fo.read(8)
            if len(s) > 0:
                samples.append(struct.unpack('<d', s)[0])
            else:
                break
    
        return (samples, sample_period)

        
def remove_short_se0s(diff_edges, min_se0_time):
    se0_start = None
    
    # Don't filter the first edge
    try:
        edge = next(diff_edges)
    except StopIteration:
        raise StopIteration #FIX
        
    #yield edge
    
    merged_edge = False
    while True:
        prev_edge = edge
        try:
            edge = next(diff_edges)
        except StopIteration:
            break
            
        if edge[1] != 0:
            merged_edge = False

        if se0_start is not None: # prev edge started SE0
            se0_end = edge[0]
            se0_len = se0_end - se0_start
            
            if se0_len < min_se0_time:
                # merge edges and remove SE0
                prev_edge = ((se0_start + se0_end) / 2.0, edge[1])
                merged_edge = True
                yield prev_edge
            else:
                merged_edge = False

            se0_start = None

        if edge[1] == 0: #SE0
            se0_start = edge[0]

        if not merged_edge:
            yield prev_edge

    yield prev_edge # last edge
            
        
def test_diff_usb_file():
    dp_samples, sample_period = read_bin_file('test/data/usb_dp.bin')
    dm_samples, sample_period = read_bin_file('test/data/usb_dm.bin')
    time_samples = [i*sample_period for i in xrange(len(dp_samples))]
    
    # generate differential waveform
    d_diff_samples = [s[0] - s[1] for s in zip(dp_samples, dm_samples)]
    
    dp_s = zip(time_samples, dp_samples)
    dm_s = zip(time_samples, dm_samples)
    
    d_diff_s = zip(time_samples, d_diff_samples)
    
    
    plt.clf()
    dp_s2 = [s + 4.0 for s in dp_samples]
    plt.plot(time_samples, dp_s2)
    plt.plot(time_samples, dm_samples)
    
    plt.plot(time_samples, d_diff_samples)


    # generate single-ended edge waveforms
    logic = find_logic_levels(iter(dp_s), max_samples=5000, buf_size=2000)
    hyst = 0.4
    dp_e = list(find_edges(iter(dp_s), logic, hysteresis=hyst))
    dm_e = list(find_edges(iter(dm_s), logic, hysteresis=hyst))
    
    dp_e_t, dp_e_wf = zip(*list(sample_edge_list(iter(dp_e), sample_period, 1.0e-6)))
    dm_e_t, dm_e_wf = zip(*list(sample_edge_list(iter(dm_e), sample_period, 1.0e-6)))
    
    plt.plot(dp_e_t, dp_e_wf)
    plt.plot(dm_e_t, dm_e_wf)
    
    # generate differential edge waveform
    d_logic = find_logic_levels(iter(d_diff_s), max_samples=5000, buf_size=2000)
    hyst = 0.1
    d_diff_e = list(find_differential_edges(iter(d_diff_s), d_logic, hysteresis=hyst))
    print('DIFF edges', d_diff_e, '\n')
    
    min_se0 = 60.0e-9
    filt1 = list(remove_short_se0s(iter(d_diff_e), min_se0))
    print('FILTER:', list(iter(filt1)), '\n')
    print('FILTER 2:', list(remove_short_se0s(iter(filt1), min_se0)), '\n')
    
    d_diff_e = list(remove_short_se0s(remove_short_se0s(iter(d_diff_e), min_se0), min_se0))
    #print('FILTERED edges', d_diff_e)
    
    dd_e_t, dd_e_wf = zip(*list(sample_edge_list(iter(d_diff_e), sample_period, 1.0e-6)))
    
    plt.plot(dd_e_t, dd_e_wf)
    
    #print('logic', logic)
    #print('dp_e', dp_e)
    #print('dm_e', dm_e)
    
    plt.show()
    
    records_it = usb_diff_decode(iter(d_diff_e), stream_type=StreamType.Edges)
    records = list(records_it)
    
    print('*************** decoded records', len(records))
    for r in records:
        if r.kind == 'USB packet':
            print('{}, {}'.format((r.start_time, r.end_time), r.packet))
        elif r.kind == 'USB error':
            print('{}, {}'.format((r.start_time, r.end_time), r))
    
def test_usb_file():
    dp_samples, sample_period = read_bin_file('test/data/usb_dp.bin')
    dm_samples, sample_period = read_bin_file('test/data/usb_dm.bin')
    time_samples = [i*sample_period for i in xrange(len(dp_samples))]
    
    dp_s = zip(time_samples, dp_samples)
    dm_s = zip(time_samples, dm_samples)
    
    
    plt.clf()
    dp_s2 = [s + 4.0 for s in dp_samples]
    plt.plot(time_samples, dp_s2)
    plt.plot(time_samples, dm_samples)

    
    logic = find_logic_levels(iter(dp_s), max_samples=5000, buf_size=2000)
    hyst = 0.4
    dp_e = list(find_edges(iter(dp_s), logic, hysteresis=hyst))
    dm_e = list(find_edges(iter(dm_s), logic, hysteresis=hyst))
    
    dp_e_t, dp_e_wf = zip(*list(sample_edge_list(iter(dp_e), sample_period, 1.0e-6)))
    dm_e_t, dm_e_wf = zip(*list(sample_edge_list(iter(dm_e), sample_period, 1.0e-6)))
    
    plt.plot(dp_e_t, dp_e_wf)
    plt.plot(dm_e_t, dm_e_wf)
    
    #print('logic', logic)
    #print('dp_e', dp_e)
    #print('dm_e', dm_e)
    
    plt.show()
    
    
    records_it = usb_decode(iter(dp_s), iter(dm_s), stream_type=StreamType.Samples)
    records = list(records_it)
    
    print('*************** decoded records', len(records))
    for r in records:
        if r.kind == 'USB packet':
            print('{}, {}'.format((r.start_time, r.end_time), r.packet))
        elif r.kind == 'USB error':
            print('{}, {}'.format((r.start_time, r.end_time), r))


def test_usb():
    speed = USBSpeed.FullSpeed

    p = USBTokenPacket(USBPID.TokenIn, 0x7F, 1, speed=speed)
    p2 = USBTokenPacket(USBPID.TokenIn, 124, 1, delay=30.0e-7, speed=speed)
    p3 = USBDataPacket(USBPID.Data0, [1,2,3,4,5,0xff, 0xff, 0xff], speed=speed)
    p4 = USBHandshakePacket(USBPID.ACK, speed=speed)
    p5 = USBSOFPacket(USBPID.SOF, 0x123, speed=speed)
    p6 = USBEXTPacket(USBPID.EXT, 0x22, 0x03, 0xA, 0x1A0, speed=speed)
    p7 = USBSplitPacket(USBPID.SPLIT, 0x11, 0, 0x10, 1, 0, 0x1, speed=speed)
    
    p4.hs_sync_dropped_bits = 18
    
    #packets = [p, p2, p3, p4, p5, p6]
    
    packets = [p, p2, p4, p5, p3]
    packets = [p, p2, p6, p5]
    packets = [p4, p4]
    
    dp, dm = zip(*list(usb_synth(packets, 1.0e-7, 3.0e-7)))
    
    dp = list(remove_excess_edges(iter(dp)))
    dm = list(remove_excess_edges(iter(dm)))
    
    sr = USBClockPeriod[speed] / 10.0
    dm_t, dm_wf = zip(*list(sample_edge_list(iter(dm), sr)))
    dp_t, dp_wf = zip(*list(amplify(sample_edge_list(iter(dp), sr), 1.0, 1.1)))
    
    records_it = usb_decode(iter(dp), iter(dm), stream_type=StreamType.Edges)
    
    records = list(records_it)
    
    print('*************** decoded records', len(records))
    for r in records:
        if r.kind == 'USB packet':
            print('{}, {}'.format((r.start_time, r.end_time), r.packet))
        elif r.kind == 'USB error':
            print('{}, {}'.format((r.start_time, r.end_time), r))
    
    
    # create differential signal
    d_diff = list(sum_streams(iter(zip(dp_t, dp_wf)), invert(iter(zip(dm_t, dm_wf))) ))
    d_diff_t, d_diff_wf = zip(*list(amplify(iter(d_diff), 0.2, 0.5)))
    
    
    plt.clf()
    plt.plot(dp_t, dp_wf)
    plt.plot(dm_t, dm_wf)
    plt.plot(d_diff_t, d_diff_wf)
    plt.ylim(-0.05, 2.25)
    plt.show()


def test_i2c():
    clk_freq = 100.0e3

    transfers = []
    transfers.append(I2CTransfer(I2C.Write, 0x23, [1,2,3, 4]))
    transfers.append(I2CTransfer(I2C.Write, 0x183, [5, 6, 240]))
    scl, sda = zip(*list(i2c_synth(transfers, clk_freq, idle_start=3.0e-5, idle_end=3.0e-5)))
    
    scl = list(remove_excess_edges(iter(scl)))
    sda = list(remove_excess_edges(iter(sda)))
    
    sr = 1.0 / (clk_freq * 20.0)
    scl_t, scl_wf = zip(*list(sample_edge_list(iter(scl), sr)))
    sda_t, sda_wf = zip(*list(amplify(sample_edge_list(iter(sda), sr), 0.8, 0.1)))
    
    
    records = i2c_decode(iter(scl), iter(sda), stream_type=StreamType.Edges)
    records = list(records)
    
    print('Decoded:', [str(r) for r in records])
    
    
    plt.clf()
    plt.plot(scl_t, scl_wf)
    plt.plot(sda_t, sda_wf)
    plt.ylim(-0.05, 1.25)    
    plt.show()


def test_spi():
    cpol = 0
    cpha = 1
    clock_freq = 30.0
    
    clk, mosi, cs = zip(*list(spi_synth([3, 4, 5, 240], 8, clock_freq, cpol, cpha, True, 4.0 / clock_freq, 0.0)))
    
    #print('CLK:', clk)
    #print( 'MOSI:', mosi)
    #print('CS:', cs)
    clk = list(remove_excess_edges(iter(clk)))
    mosi = list(remove_excess_edges(iter(mosi)))
    cs = list(remove_excess_edges(iter(cs)))
    
    use_edges=False
    

    if use_edges:
        records = spi_decode(iter(clk), iter(mosi), iter(cs), cpol=cpol, cpha=cpha, lsb_first=True, stream_type=StreamType.Edges)
        records = list(records)
        
        print('$$$ MOSI', mosi)
        print('$$$ CS', cs)
        print('$$$ CLK', clk)
        
        ct, clk_wf = zip(*list(sample_edge_list(iter(clk), 0.1)))
        mt, mosi_wf = zip(*list(amplify(sample_edge_list(iter(mosi), 0.1), 0.8, 0.1)))
        st, cs_wf = zip(*list(amplify(sample_edge_list(iter(cs), 0.1), 0.6, 0.2)))

        plt.clf()
        plt.plot(ct, clk_wf)
        plt.plot(mt, mosi_wf)
        plt.plot(st, cs_wf)
        plt.ylim(-0.05, 1.25)
        
    else:
    
        #frames = spi_decode_2(iter(clk), iter(mosi), iter(cs), cpol=cpol, cpha=cpha, lsb_first=True)
        sr = 10.0e-2
        sr = 1.0 / (20.0 * clock_freq)
        # #print('>>>>>', len(list(sample_edge_list(iter(clk), sr))))
        # ct, clk_wf = zip(*list(sample_edge_list(iter(clk), sr)))
        # print('logic>', find_logic_levels(noisify(sample_edge_list(iter(clk), sr)), max_samples=10000))
        # plt.plot(ct, clk_wf)
        # plt.show()

        clk_s = list(sample_edge_list(iter(clk), sr))
        #clk_s = list(noisify(sample_edge_list(iter(clk), sr), 30.0))
        mosi_s = list(noisify(sample_edge_list(iter(mosi), sr)))
        cs_s = list(noisify(sample_edge_list(iter(cs), sr)))
        
        #print('                  SEL >>> ', cs_s[-1])
        
        records = spi_decode(iter(clk_s), iter(mosi_s), iter(cs_s), cpol=cpol, cpha=cpha, lsb_first=True)
        
        records = list(records)
        
        ct, clk_wf = zip(*clk_s)
        mt, mosi_wf = zip(*mosi_s)
        st, cs_wf = zip (*cs_s)
        
        logic = find_logic_levels(iter(clk_s), max_samples=5000, buf_size=2000)
        clk_e = list(find_edges(iter(clk_s), logic, hysteresis=0.4))
        mosi_e = list(find_edges(iter(mosi_s), logic, hysteresis=0.4))
        cs_e =   list(find_edges(iter(cs_s), logic, hysteresis=0.4))
        
        print('$$$ MOSI', mosi_e)
        print('$$$ CS', cs_e)
        print('$$$ CLK', clk_e)
        #ce_t, clk_e_wf = zip(*list(clk_e))
        
        # #print(clk_wf[:100])

        plt.clf()
        plt.plot(ct, clk_wf)
        plt.plot(mt, mosi_wf)
        plt.plot(st, cs_wf)
        #plt.plot(ce_t, clk_e_wf)
        plt.ylim(-0.05, 1.25)

    print('Decoded:', [str(r) for r in records])
        
    ax = plt.axes()
    text_height = 1.05
    rect_top = 1.15
    rect_bot = -0.05
    for r in records:
        if r.kind == 'SPI frame':
            plt.text((r.start_time + r.end_time) / 2.0, text_height, str(r))
            color = 'orange' if r.nested_status() < 200 else 'red'
            rect = pts.Rectangle((r.start_time, rect_bot), width=r.end_time - r.start_time, height=rect_top - rect_bot, facecolor=color,  alpha=0.2)
            ax.add_patch(rect)    
    
    plt.show()

def test_uart():

    #rise_time = 1.0e-6
    #sample_rate = 10.0e6
    
    #sample_rate = 4.0 / rise_time
    
    
    # edge_bw = 0.35 / rise_time
    
    # print('edge bandwidth: {0:,}'.format(edge_bw))
    
    msg = '9rYQ\_R;N\J\0I`v8\cR'
    baud = 128000
    parity=None
    bits=8
    
    msg = 'iJ[hOH5H<4Cl@q_wW?ss'
    baud = 460800
    parity = 'odd'
    bits = 7
    
    msg = 'L`kVRZn1M60YLO@c?4un'
    #msg = 'L`kVRZ'
    baud = 110
    parity = None
    bits = 8
    
    sample_rate = baud * 100.0
    rise_time = 0.35 * 2.0 / sample_rate * 10.0 # 10x min rise time
    
    print('sample rate', sample_rate)
    
    edges = uart_synth(bytearray(msg), bits, baud, parity=parity, idle_start=100.0 / sample_rate)
    elist = list(edges)
    print('elist len', len(elist))
    print('elist:', elist)
    edges = iter(elist)
    
    
    samples = synth_wave(edges, sample_rate, rise_time, ripple_db=60)
    
    noisy = amplify(noisify(samples, snr_db=30.0), gain=-15.0)
    
    #t = np.arange(len(noisy)) / sample_rate
    
    #print('{0} samples'.format(len(noisy)))
        
    # plt.plot(t, noisy)
    # plt.ylim(-0.05, 1.75)
    # plt.show()
    
    #plt.figure(2)
    #plt.plot(sp.fft(noisy)[:len(noisy)/2])

    #print(edges[:10])
    
    #t, o_noisy = zip(*noisy)
    #plt.plot(t, o_noisy)
    #plt.show()
    
    waveform = list(noisy) #list(dropout(noisy,2.0e-3,2.1e-3))
    t, wf = zip(*waveform)
    
    # os = OnlineStats()
    # sd_wf = []
    # m_wf = []
    # i = 0
    # for s in wf:
        # os.accumulate(s)
        # sd_wf.append(3 * os.std())
        # m_wf.append(s - os.mean())
        # i += 1
        # if i > 3 and abs(s - os.mean()) > (3 * os.std()):
            # i = 0
            # os.reset()

    
    bd = deque()
    frames = uart_decode(iter(waveform), bits=bits, inverted=False, parity=parity, baud_rate=None, baud_deque=bd)
    #frames = uart_decode(iter(waveform), bits=bits, inverted=False, parity=parity, baud_rate=baud, baud_deque=bd)
    #frames = uart_decode(iter(elist), bits=bits, inverted=True, parity=parity, baud_rate=baud, baud_deque=bd, stream_type=StreamType.Edges)
    frames = list(frames)
    print(''.join(str(d) for d in frames))
    bd = bd.pop()
    print(bd)
    print('edges len', len(bd['edges']))

    plt.plot(t, wf)
    # plt.plot(t, sd_wf)
    # plt.plot(t, m_wf)
    ax = plt.axes()
    
    elt, elwf = zip(*elist)
    plt.plot(elt, elwf)
    
    
    logic = find_logic_levels(iter(waveform), 5000, 2000)
    span = logic[1] - logic[0]
    rect_top = logic[1] + span * 0.15
    rect_bot = logic[0] - span * 0.05
    
    text_height = logic[1] + rect_top / 2.0
    
    #plt.ylim(rect_bot - span * 0.1, rect_top + span * 0.1)
    
    print('Logic levels:', logic)
    
    print('frames:', frames)
    
    for f in frames:
        plt.text((f.start_time + f.end_time) / 2.0, text_height, str(f))
        color = 'orange' if f.nested_status() < 200 else 'red'
        rect = pts.Rectangle((f.start_time, rect_bot), width=f.end_time - f.start_time, height=rect_top - rect_bot, facecolor=color,  alpha=0.2)
        ax.add_patch(rect)

    # hist, _ = np.histogram(wf, bins=60)
    # hpeaks = find_hist_peaks(hist)
    # print('## hpeaks', hpeaks)
    
    # b, t = find_bot_top_hist_peaks(wf[:5000], 60)
    # print('## b, t', b, t)
        
    # plt.figure(2)
    # plt.hist(wf, bins=60)
    
    plt.show()
    

    
    # print('End time:', frames[-1].end_time)
    # for x in frames:
        # pass
        # print('fc', x.data, chr(x.data))
    
    # for f in frames:
        # print(repr(f))
        # for sf in f.subframes:
            # print('  {0}'.format(repr(sf)))
        
    
    
    #plt.figure(2)
    #plt.plot(s)
    
    
    #plt.show()
    
        

if __name__ == '__main__':
    print('Serial decode test tool')

    parser = OptionParser()
    parser.add_option('-u', dest='uart', action='store_true', default=False, help='uart test')
    parser.add_option('-s', dest='spi', action='store_true', default=False, help='spi test')
    parser.add_option('-i', dest='i2c', action='store_true', default=False, help='i2c test')
    parser.add_option('-b', dest='usb', action='store_true', default=False, help='usb test')
    parser.add_option('-f', dest='usb_file', action='store_true', default=False, help='usb file test')
    
    options, args = parser.parse_args()
    
    if options.uart:
        print('  Testing UART')
        test_uart()
        
    if options.spi:
        print('  Testing SPI')
        test_spi()

    if options.i2c:
        print('  Testing I2C')
        test_i2c()

    if options.usb:
        print('  Testing USB')
        test_usb()
        
    if options.usb_file:
        print('  Testing USB file')
        test_diff_usb_file()
