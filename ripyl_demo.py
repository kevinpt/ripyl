#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   Ripyl demo script
'''

# Copyright © 2013 Kevin Thibedeau

# This file is part of Ripyl.

# Ripyl is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.

# Ripyl is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with Ripyl. If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function, division

import sys
from optparse import OptionParser

import random

import ripyl
import ripyl.protocol.uart as uart
import ripyl.protocol.spi as spi
import ripyl.protocol.i2c as i2c
import ripyl.protocol.usb as usb
import ripyl.protocol.ps2 as ps2
import ripyl.protocol.iso_k_line as kline
import ripyl.sigproc as sigp
import ripyl.streaming as stream
import ripyl.util.eng as eng
from ripyl.sigproc import min_rise_time

try:
    import matplotlib
    matplotlib_exists = True
except ImportError:
    matplotlib_exists = False

if matplotlib_exists:
    import ripyl.util.plot as rplot

def main():
    '''Entry point for script'''

    protocols = ('uart', 'i2c', 'spi', 'usb', 'usb-diff', 'hsic', 'ps2', 'kline')

    usage = '''%prog [-p PROTOCOL] [-n] [-m MSG]
    
Supported protocols:
  {}
    '''.format(', '.join(protocols))
    parser = OptionParser(usage=usage)
    
    parser.add_option('-p', '--protocol', dest='protocol', default='uart', help='Specify protocol to use')
    parser.add_option('-n', '--no-plot', dest='no_plot', action='store_true', default=False, help='Disable matplotlib plotting')
    parser.add_option('-m', '--msg', dest='msg', default='Hello, world!', help='Input message')
    parser.add_option('-s', '--snr', dest='snr_db', default=30.0, type=float, help='SNR in dB')
    parser.add_option('-b', '--baud', dest='baud', type=float, help='Baud rate')
    parser.add_option('-o', '--save-plot', dest='save_file', help='Save plot to image file')
    parser.add_option('-d', '--dropout', dest='dropout', help='Dropout signal from "start,end[,level]"')
    parser.add_option('-t', '--title', dest='title', help='Title for plot')
    parser.add_option('-f', '--figsize', dest='figsize', help='Figure size (w,h) in inches')
    
    options, args = parser.parse_args()
    
    if not matplotlib_exists:
        options.no_plot = True

    # process dropout parameters
    if options.dropout is not None:
        do_opts = [float(n) for n in options.dropout.split(',')]
        if len(do_opts) == 3:
            options.dropout_level = do_opts[2]
            do_opts = do_opts[0:2]
        else:
            options.dropout_level = 0.0
        options.dropout = do_opts

    if options.figsize is not None:
        options.figsize = [float(x) for x in options.figsize.split(',')]
        

        
    options.protocol = options.protocol.lower()

    print('** Ripyl demo **\n\n')
    
    if options.protocol == 'uart':
        demo_uart(options)
    elif options.protocol == 'i2c':
        demo_i2c(options)
    elif options.protocol == 'spi':
        demo_spi(options)
    elif options.protocol in ['usb', 'usb-diff', 'hsic']:
        demo_usb(options)
    elif options.protocol == 'ps2':
        demo_ps2(options)
    elif options.protocol == 'kline':
        demo_iso_k_line(options)
    else:
        print('Unrecognized protocol: "{}"'.format(options.protocol))
        sys.exit(1)


def demo_usb(options):
    print('USB protocol\n')
    
    # USB params
    bus_speed = usb.USBSpeed.HighSpeed
    clock_freq = 1.0 / usb.USBClockPeriod[bus_speed]
    
    # Sampled waveform params
    sample_rate = clock_freq * 10.0
    rise_time = min_rise_time(sample_rate) * 8.0 # 8x min. rise time
    noise_snr = options.snr_db
    
    message = options.msg
    byte_msg = bytearray(message.encode('latin1')) # Get raw bytes as integers
    
    packets = [usb.USBDataPacket(usb.USBPID.Data0, byte_msg, speed=bus_speed)]
    #packets.append(usb.USBSplitPacket(usb.USBPID.SPLIT, 0x09, 1, 0x0F, 1, 1, 1, bus_speed))
    #packets = [usb.USBSplitPacket(usb.USBPID.SPLIT, 0x09, 1, 0x0F, 1, 1, 1, bus_speed)]
    #packets = [usb.USBHandshakePacket(usb.USBPID.NYET, bus_speed, 0.0)]
    #packets = [usb.USBEXTPacket(usb.USBPID.EXT, 0x16, 0xa, 0x2, 0x31f, bus_speed)]
    #packets.append(usb.USBTokenPacket(usb.USBPID.TokenOut, 0x6c, 0x2, bus_speed))
    #packets.append(usb.USBSOFPacket(usb.USBPID.SOF, 0x12, bus_speed))
    #packets = [usb.USBTokenPacket(usb.USBPID.TokenOut, 0x07, 0x01, bus_speed)]
    # m1 = bytearray('Ripyl supports')
    # packets.append(usb.USBDataPacket(usb.USBPID.Data0, m1, bus_speed))
    # packets.append(usb.USBHandshakePacket(usb.USBPID.ACK, bus_speed))
    # packets.append(usb.USBTokenPacket(usb.USBPID.TokenOut, 0x07, 0x01, bus_speed, delay=0.8e-7))
    # m2 = bytearray('USB 2.0 HS')
    # packets.append(usb.USBDataPacket(usb.USBPID.Data1, m2, bus_speed))
    # packets.append(usb.USBHandshakePacket(usb.USBPID.ACK, bus_speed))

    if options.protocol == 'usb':
        # Synthesize the waveform edge stream
        # This can be fed directly into usb_decode() if an analog waveform is not needed
        dp, dm = usb.usb_synth(packets, idle_end=0.2e-7)
        
        # Convert to a sample stream with band-limited edges and noise
        
        cln_dp_it = sigp.synth_wave(dp, sample_rate, rise_time)
        cln_dm_it = sigp.synth_wave(dm, sample_rate, rise_time)
        
        gain = 0.4 if bus_speed == usb.USBSpeed.HighSpeed else 3.3
        nsy_dp_it = sigp.amplify(sigp.noisify(cln_dp_it, snr_db=noise_snr), gain=gain, offset=0.0)
        nsy_dm_it = sigp.amplify(sigp.noisify(cln_dm_it, snr_db=noise_snr), gain=gain, offset=0.0)


        # Dropout needs to flip both D+ and D- to be useful for error injection
        # if options.dropout is not None:
            # do_start, do_end = [float(n) for n in options.dropout.split(',')]
            # nsy_dm_it = sigp.dropout(nsy_dm_it, do_start, do_end)
        
        # Capture the samples from the iterator
        nsy_dp = list(nsy_dp_it)
        nsy_dm = list(nsy_dm_it)
        
        # Decode the samples
        decode_success = True
        records = []
        try:
            records_it = usb.usb_decode(iter(nsy_dp), iter(nsy_dm))
            records = list(records_it)
            
        except stream.StreamError as e:
            print('Decode failed:\n  {}'.format(e))
            decode_success = False
    elif options.protocol == 'usb-diff': # differential usb
        # Synthesize the waveform edge stream
        # This can be fed directly into usb_diff_decode() if an analog waveform is not needed
        diff_d = usb.usb_diff_synth(packets, idle_end=0.2e-7)
        
        # Convert to a sample stream with band-limited edges and noise
        
        cln_dd_it = sigp.synth_wave(diff_d, sample_rate, rise_time)
        
        nsy_dd_it = sigp.amplify(sigp.noisify(cln_dd_it, snr_db=noise_snr), gain=3.3, offset=0.0)


        # Dropout needs to flip both D+ and D- to be useful for error injection
        # if options.dropout is not None:
            # do_start, do_end = [float(n) for n in options.dropout.split(',')]
            # nsy_dm_it = sigp.dropout(nsy_dm_it, do_start, do_end)
        
        # Capture the samples from the iterator
        nsy_dd = list(nsy_dd_it)
        
        # Decode the samples
        decode_success = True
        records = []
        try:
            records_it = usb.usb_diff_decode(iter(nsy_dd))
            records = list(records_it)
            
        except stream.StreamError as e:
            print('Decode failed:\n  {}'.format(e))
            decode_success = False

    else: # HSIC
        # Force all packets to HighSpeed

        # Synthesize the waveform edge stream
        # This can be fed directly into usb_hsic_decode() if an analog waveform is not needed
        strobe, data = usb.usb_hsic_synth(packets, idle_end=0.2e-7)
        
        # Convert to a sample stream with band-limited edges and noise
        
        cln_stb_it = sigp.synth_wave(strobe, sample_rate, rise_time)
        cln_d_it = sigp.synth_wave(data, sample_rate, rise_time)

        cln_stb = list(cln_stb_it)
        cln_stb_it = iter(cln_stb)
        
        gain = 1.2
        nsy_stb_it = sigp.amplify(sigp.noisify(cln_stb_it, snr_db=noise_snr), gain=gain, offset=0.0)
        nsy_d_it = sigp.amplify(sigp.noisify(cln_d_it, snr_db=noise_snr), gain=gain, offset=0.0)


        # Dropout needs to flip both D+ and D- to be useful for error injection
        # if options.dropout is not None:
            # do_start, do_end = [float(n) for n in options.dropout.split(',')]
            # nsy_dm_it = sigp.dropout(nsy_dm_it, do_start, do_end)
        
        # Capture the samples from the iterator
        nsy_stb = list(nsy_stb_it)
        nsy_d = list(nsy_d_it)
        
        # Decode the samples
        decode_success = True
        records = []
        try:
            records_it = usb.usb_hsic_decode(iter(nsy_stb), iter(nsy_d))
            records = list(records_it)
            
        except stream.StreamError as e:
            print('Decode failed:\n  {}'.format(e))
            decode_success = False


    # Report results
    print('\nProtocol parameters:')
    print('  bus speed:', usb.USBSpeed(bus_speed))
    print('  clock frequency:', eng.eng_si(clock_freq, 'Hz'))
    print('  message:', message)

    print('Waveform parameters:')
    print('  sample rate:', eng.eng_si(sample_rate, 'Hz'))
    print('  rise time:', eng.eng_si(rise_time, 's', 1))
    print('  SNR:', noise_snr, 'dB')

    if decode_success:
        decoded_msg = ''
        for r in records:
            if r.kind == 'USB packet' and hasattr(r.packet, 'data'):
                decoded_msg = ''.join([chr(b) for b in r.packet.data])
                break
            
        print('\nDecoded message:', decoded_msg)
        if decoded_msg == message:
            print('  (matches input message)')
        else:
            print('  (MISMATCH to input message)')

            
    if any(r.nested_status() != stream.StreamStatus.Ok for r in records):
        print('\nDecode errors:')
        for i, r in enumerate(records):
            if r.nested_status() != stream.StreamStatus.Ok:
                status_name = usb.USBStreamStatus(r.nested_status())
                print('  record {}: status = {}'.format(i, status_name))

    if not options.no_plot:
        if options.protocol == 'usb':
            channels = {'dp':nsy_dp, 'dm':nsy_dm}
        elif options.protocol == 'usb-diff':
            channels = {'dd':nsy_dd}
        else: # HSIC
            channels = {'strobe':nsy_stb, 'data':nsy_d}

        if options.title is not None:
            title = options.title
        else:
            title = 'USB Simulation'
        rplot.usb_plot(channels, records, title, save_file=options.save_file, figsize=options.figsize)

        
def demo_spi(options):
    print('SPI protocol\n')
    
    # SPI params
    clock_freq = 5.0e6
    word_size = 8
    cpol = 0
    cpha = 0
    
    # Sampled waveform params
    sample_rate = clock_freq * 100.0
    rise_time = min_rise_time(sample_rate) * 10.0 # 10x min. rise time
    noise_snr = options.snr_db
    
    message = options.msg
    byte_msg = bytearray(message.encode('latin1')) # Get raw bytes as integers


    # Synthesize the waveform edge stream
    # This can be fed directly into spi_decode() if an analog waveform is not needed
    clk, data_io, cs = spi.spi_synth(byte_msg, word_size, clock_freq, cpol, cpha)
    
    # Convert to a sample stream with band-limited edges and noise
    cln_clk_it = sigp.synth_wave(clk, sample_rate, rise_time)
    cln_data_io_it = sigp.synth_wave(data_io, sample_rate, rise_time)
    cln_cs_it = sigp.synth_wave(cs, sample_rate, rise_time)
    
    nsy_clk_it = sigp.amplify(sigp.noisify(cln_clk_it, snr_db=noise_snr), gain=3.3, offset=0.0)
    nsy_data_io_it = sigp.amplify(sigp.noisify(cln_data_io_it, snr_db=noise_snr), gain=3.3, offset=0.0)
    nsy_cs_it = sigp.amplify(sigp.noisify(cln_cs_it, snr_db=noise_snr), gain=3.3, offset=0.0)
    
    if options.dropout is not None:
        nsy_data_io_it = sigp.dropout(nsy_data_io_it, options.dropout[0], options.dropout[1], options.dropout_level)
    
    # Capture the samples from the iterator
    nsy_clk = list(nsy_clk_it)
    nsy_data_io = list(nsy_data_io_it)
    nsy_cs = list(nsy_cs_it)
    
    # Decode the samples
    decode_success = True
    records = []
    try:
        records_it = spi.spi_decode(iter(nsy_clk), iter(nsy_data_io), iter(nsy_cs), cpol, cpha)
        records = list(records_it)
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False


    # Report results
    print('\nProtocol parameters:')
    print('  clock frequency:', eng.eng_si(clock_freq, 'Hz'))
    print('  word size:', word_size)
    print('  cpol:', cpol)
    print('  cpha:', cpha)
    print('  message:', message)

    print('Waveform parameters:')
    print('  sample rate:', eng.eng_si(sample_rate, 'Hz'))
    print('  rise time:', eng.eng_si(rise_time, 's', 1))
    print('  SNR:', noise_snr, 'dB')

    if decode_success:
        decoded_msg = ''
        for r in records:
            if r.kind == 'SPI frame':
                decoded_msg += chr(r.data)
            
        print('\nDecoded message:', decoded_msg)
        if decoded_msg == message:
            print('  (matches input message)')
        else:
            print('  (MISMATCH to input message)')

            
    if any(r.nested_status() != stream.StreamStatus.Ok for r in records):
        print('\nDecode errors:')
        for i, r in enumerate(records):
            if r.nested_status() != stream.StreamStatus.Ok:
                status_name = StreamRecord.status_text(r.nested_status())
                print('  record {}: status = {}'.format(i, status_name))

    if not options.no_plot:
        if options.title is not None:
            title = options.title
        else:
            title = 'SPI Simulation'
        rplot.spi_plot({'clk':nsy_clk, 'data_io':nsy_data_io, 'cs':nsy_cs}, records, title, save_file=options.save_file, \
            figsize=options.figsize)


def demo_i2c(options):
    print('I2C protocol\n')
    
    # I2C params
    clock_freq = 100.0e3
    
    # Sampled waveform params
    sample_rate = clock_freq * 100.0
    rise_time = min_rise_time(sample_rate) * 10.0 # 10x min. rise time
    noise_snr = options.snr_db
    
    message = options.msg
    byte_msg = bytearray(message.encode('latin1')) # Get raw bytes as integers
    
    transfers = []
    transfers.append(i2c.I2CTransfer(i2c.I2C.Write, 0x42, byte_msg))
    
    
    # Synthesize the waveform edge stream
    # This can be fed directly into i2c_decode() if an analog waveform is not needed
    scl, sda = i2c.i2c_synth(transfers, clock_freq, idle_start=3.0e-5, idle_end=3.0e-5)
    
    # Convert to a sample stream with band-limited edges and noise
    cln_scl_it = sigp.synth_wave(scl, sample_rate, rise_time)
    cln_sda_it = sigp.synth_wave(sda, sample_rate, rise_time)
    
    nsy_scl_it = sigp.amplify(sigp.noisify(cln_scl_it, snr_db=noise_snr), gain=3.3, offset=0.0)
    nsy_sda_it = sigp.amplify(sigp.noisify(cln_sda_it, snr_db=noise_snr), gain=3.3, offset=0.0)
    
    if options.dropout is not None:
        nsy_sda_it = sigp.dropout(nsy_sda_it, options.dropout[0], options.dropout[1], options.dropout_level)
    
    # Capture the samples from the iterator
    nsy_scl = list(nsy_scl_it)
    nsy_sda = list(nsy_sda_it)
    

    # Decode the samples
    decode_success = True
    records = []
    try:
        records_it = i2c.i2c_decode(iter(nsy_scl), iter(nsy_sda))
        records = list(records_it)
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False


    # Report results
    print('\nProtocol parameters:')
    print('  clock frequency:', eng.eng_si(clock_freq, 'Hz'))
    print('  message:', message)

    print('Waveform parameters:')
    print('  sample rate:', eng.eng_si(sample_rate, 'Hz'))
    print('  rise time:', eng.eng_si(rise_time, 's', 1))
    print('  SNR:', noise_snr, 'dB')

    if decode_success:
        decoded_msg = ''
        for r in records:
            if r.kind == 'I2C byte':
                decoded_msg += chr(r.data)
            
        print('\nDecoded message:', decoded_msg)
        if decoded_msg == message:
            print('  (matches input message)')
        else:
            print('  (MISMATCH to input message)')

            
    if any(r.nested_status() != stream.StreamStatus.Ok for r in records):
        print('\nDecode errors:')
        for i, r in enumerate(records):
            if r.nested_status() != stream.StreamStatus.Ok:
                status_name = StreamRecord.status_text(r.nested_status())
                print('  record {}: status = {}'.format(i, status_name))

    if not options.no_plot:
        if options.title is not None:
            title = options.title
        else:
            title = 'I2C Simulation'
        rplot.i2c_plot({'scl':nsy_scl, 'sda':nsy_sda}, records, title, save_file=options.save_file, figsize=options.figsize)
        


def demo_uart(options):
    print('UART protocol\n')
    
    # UART params
    baud = 115200
    parity = 'even' # One of None, 'even', or 'odd'
    bits = 8 # Can be the standard 5,6,7,8,9 or anything else
    stop_bits = 1 # Can use 1, 1.5 or 2 (Or any number greater than 0.5 actualy)
    polarity = uart.UARTConfig.IdleHigh

    # Sampled waveform params
    sample_rate = baud * 100.0
    rise_time = min_rise_time(sample_rate) * 10.0 # 10x min. rise time
    noise_snr = options.snr_db
    
    message = options.msg

    byte_msg = bytearray(message.encode('latin1')) # Get raw bytes as integers
    
    # Synthesize the waveform edge stream
    # This can be fed directly into uart_decode() if an analog waveform is not needed
    edges_it = uart.uart_synth(byte_msg, bits, baud, parity, stop_bits, idle_start=8.0 / baud, idle_end=8.0 / baud)
    
    # Convert to a sample stream with band-limited edges and noise
    clean_samples_it = sigp.synth_wave(edges_it, sample_rate, rise_time)
    
    noisy_samples_it = sigp.quantize(sigp.amplify(sigp.noisify(clean_samples_it, snr_db=noise_snr), gain=15.0, offset=-5), 50.0)
    if options.dropout is not None:
        noisy_samples_it = sigp.dropout(noisy_samples_it, options.dropout[0], options.dropout[1], options.dropout_level)
    
    # Capture the samples from the iterator
    noisy_samples = list(noisy_samples_it)
    

    # Decode the samples
    decode_success = True
    records = []
    try:
        records_it = uart.uart_decode(iter(noisy_samples), bits, parity, stop_bits, polarity=polarity, \
            baud_rate=options.baud)
        records = list(records_it)
    except uart.AutoBaudError as e:
        print('Decode failed:\n  {}'.format(e))
        print('\nTry using a longer message or using the --baud option.')
        print('Auto-baud requires about 50 edge transitions to be reliable.')
        decode_success = False
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False


    # Report results
    print('\nProtocol parameters:')
    print('  baud:', baud)
    print('  decode baud:', options.baud)
    print('  bits:', bits)
    print('  parity:', parity)
    print('  stop bits:', stop_bits)
    print('  polarity:', uart.UARTConfig(polarity))
    print('  message:', message)

    print('Waveform parameters:')
    print('  sample rate:', eng.eng_si(sample_rate, 'Hz'))
    print('  rise time:', eng.eng_si(rise_time, 's', 1))
    print('  SNR:', noise_snr, 'dB')

    if decode_success:
        decoded_msg = ''.join(str(r) for r in records)
        print('\nDecoded message:', decoded_msg)
        if decoded_msg == message:
            print('  (matches input message)')
        else:
            print('  (MISMATCH to input message)')

    if any(r.nested_status() != stream.StreamStatus.Ok for r in records):
        print('\nDecode errors:')
        for i, r in enumerate(records):
            if r.nested_status() != stream.StreamStatus.Ok:
                status_name = uart.UARTStreamStatus(r.nested_status())
                print('  record {}: status = {}'.format(i, status_name))

    if not options.no_plot:
        if options.title is not None:
            title = options.title
        else:
            title = 'UART Simulation'
        #records = []
        rplot.uart_plot(noisy_samples, records, title, save_file=options.save_file, figsize=options.figsize)



def demo_ps2(options):
    print('PS/2 protocol\n')
    
    # PS2 params
    clock_freq = 10.0e3
    
    # Sampled waveform params
    sample_rate = clock_freq * 100.0
    rise_time = min_rise_time(sample_rate) * 10.0 # 10x min. rise time
    noise_snr = options.snr_db
    
    message = options.msg
    byte_msg = bytearray(message.encode('latin1')) # Get raw bytes as integers
    direction = [random.choice([ps2.PS2Dir.DeviceToHost, ps2.PS2Dir.HostToDevice]) for b in byte_msg]


    # Synthesize the waveform edge stream
    # This can be fed directly into spi_decode() if an analog waveform is not needed
    clk, data = ps2.ps2_synth(byte_msg, direction, clock_freq, 4 / clock_freq, 5 / clock_freq)
    
    # Convert to a sample stream with band-limited edges and noise
    cln_clk_it = sigp.synth_wave(clk, sample_rate, rise_time)
    cln_data_it = sigp.synth_wave(data, sample_rate, rise_time)
    
    nsy_clk_it = sigp.amplify(sigp.noisify(cln_clk_it, snr_db=noise_snr), gain=3.3, offset=0.0)
    nsy_data_it = sigp.amplify(sigp.noisify(cln_data_it, snr_db=noise_snr), gain=3.3, offset=0.0)
    
    if options.dropout is not None:
        nsy_data_it = sigp.dropout(nsy_data_it, options.dropout[0], options.dropout[1], options.dropout_level)
    
    # Capture the samples from the iterator
    nsy_clk = list(nsy_clk_it)
    nsy_data = list(nsy_data_it)
    
    # Decode the samples
    decode_success = True
    records = []
    try:
        records_it = ps2.ps2_decode(iter(nsy_clk), iter(nsy_data))
        records = list(records_it)
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False


    # Report results
    print('\nProtocol parameters:')
    print('  clock frequency:', eng.eng_si(clock_freq, 'Hz'))
    print('  message:', message)

    print('Waveform parameters:')
    print('  sample rate:', eng.eng_si(sample_rate, 'Hz'))
    print('  rise time:', eng.eng_si(rise_time, 's', 1))
    print('  SNR:', noise_snr, 'dB')

    if decode_success:
        decoded_msg = ''
        for r in records:
            if r.kind == 'PS/2 frame':
                decoded_msg += chr(r.data)
            
        print('\nDecoded message:', decoded_msg)
        if decoded_msg == message:
            print('  (matches input message)')
        else:
            print('  (MISMATCH to input message)')

            
    if any(r.nested_status() != stream.StreamStatus.Ok for r in records):
        print('\nDecode errors:')
        for i, r in enumerate(records):
            if r.nested_status() != stream.StreamStatus.Ok:
                status_name = ps2.PS2StreamStatus(r.nested_status()) #StreamRecord.status_text(r.nested_status())
                print('  record {}: status = {}'.format(i, status_name))

    if not options.no_plot:
        if options.title is not None:
            title = options.title
        else:
            title = 'PS/2 Simulation'
        rplot.ps2_plot({'clk':nsy_clk, 'data':nsy_data}, records, title, save_file=options.save_file, figsize=options.figsize)


def demo_iso_k_line(options):
    print('ISO K-Line protocol\n')
    
    # K-Line params
    baud = 10400

    # Sampled waveform params
    sample_rate = baud * 100.0
    rise_time = min_rise_time(sample_rate) * 10.0 # 10x min. rise time
    noise_snr = options.snr_db
    
    messages = [
        # ISO9141 supported PIDs
        [0x68, 0x6A, 0xF1, 0x01, 0x00, 0xC4],
        [0x48, 0x6B, 0xD1, 0x41, 0x00, 0xBE, 0x1E, 0x90, 0x11, 0x42],

        # ISO14230 supported PIDs
        [0x82, 0xD1, 0xF1, 0x01, 0x00, 0x45],
        [0x86, 0xF1, 0xD1, 0x41, 0x00, 0x01, 0x02, 0x03, 0x04, 0x93],

        # ISO14230 supported PIDs (4-byte header)
        [0x80, 0x02, 0xD1, 0xF1, 0x01, 0x00, 0x45],
        [0x80, 0x06, 0xF1, 0xD1, 0x41, 0x00, 0x01, 0x02, 0x03, 0x04, 0x93],

        # Sagem proprietary SID
        [0x68, 0x6A, 0xF1, 0x22, 0x00, 0x1A, 0xFF],
        [0x48, 0x6B, 0xD1, 0x62, 0x00, 0x1A, 0x00, 0x35, 0x35]
    ]    


    
    # Synthesize the waveform edge stream
    # This can be fed directly into iso_k_line_decode() if an analog waveform is not needed
    edges_it = kline.iso_k_line_synth(messages, msg_gap=8.0e-3, idle_start=8.0 / baud, idle_end=8.0 / baud)
    
    # Convert to a sample stream with band-limited edges and noise
    clean_samples_it = sigp.synth_wave(edges_it, sample_rate, rise_time)
    
    noisy_samples_it = sigp.quantize(sigp.amplify(sigp.noisify(clean_samples_it, snr_db=noise_snr), gain=12.0), 50.0)
    if options.dropout is not None:
        noisy_samples_it = sigp.dropout(noisy_samples_it, options.dropout[0], options.dropout[1], options.dropout_level)
    
    # Capture the samples from the iterator
    noisy_samples = list(noisy_samples_it)
    

    # Decode the samples
    decode_success = True
    records = []
    try:
        records_it = kline.iso_k_line_decode(iter(noisy_samples))
        records = list(records_it)
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False


    # Report results
    print('\nProtocol parameters:')
    print('  messages:')
    for msg in messages:
        print('  {}'.format(' '.join(['{:02x}'.format(b) for b in msg])))


    print('Waveform parameters:')
    print('  sample rate:', eng.eng_si(sample_rate, 'Hz'))
    print('  rise time:', eng.eng_si(rise_time, 's', 1))
    print('  SNR:', noise_snr, 'dB')

    if decode_success:
        raw_decode = []
        for r in records:
            msg = r.msg.header.bytes() + r.msg.data + [r.msg.checksum]
            raw_decode.append([b.data for b in msg])

        print('\nDecoded messages:')
        msg_match = True
        for msg, omsg in zip(raw_decode, messages):
            if msg != omsg:
                msg_match = False
                m_flag = '< MISMATCH'
            else:
                m_flag = ''
            print('  {} {}'.format(' '.join(['{:02x}'.format(b) for b in msg]), m_flag))


        if msg_match:
            print('  (matches input message)')
        else:
            print('  (MISMATCH to input message)')
                
    if any(r.nested_status() != stream.StreamStatus.Ok for r in records):
        print('\nDecode errors:')
        for i, r in enumerate(records):
            if r.nested_status() != stream.StreamStatus.Ok:
                status_name = kline.KLineStreamMessage(r.nested_status())
                print('  record {}: status = {}'.format(i, status_name))

    if not options.no_plot:
        if options.title is not None:
            title = options.title
        else:
            title = 'ISO K-Line Simulation'
        rplot.iso_k_line_plot(noisy_samples, records, title, save_file=options.save_file, \
            label_format='hex', figsize=options.figsize)


        
if __name__ == '__main__':
    main()
