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
from collections import OrderedDict

import ripyl
import ripyl.protocol.infrared as ir
import ripyl.sigproc as sigp
import ripyl.streaming as stream
import ripyl.util.eng as eng
import test.test_support as tsup
from ripyl.sigproc import min_rise_time
from ripyl.util.color import note, success, error

try:
    import matplotlib
    matplotlib_exists = True
except ImportError:
    matplotlib_exists = False

if matplotlib_exists:
    import ripyl.util.plot as rplot

def main():
    '''Entry point for script'''

    protocols = ('uart', 'ethernet', 'i2c', 'lm73', 'spi', 'i2s', 'usb', 'usb-diff', 'hsic', 'ps2', \
                'kline', 'rc5', 'rc6', 'nec', 'sirc', 'can', 'lin', 'j1850', 'j1850-pwm')

    usage = '''%prog [-p PROTOCOL] [-n] [-m MSG]
    
Supported protocols:
  {}
    '''.format(', '.join(protocols))
    parser = OptionParser(usage=usage)
    
    parser.add_option('-p', '--protocol', dest='protocol', default='uart', help='Specify protocol to use')
    parser.add_option('-n', '--no-plot', dest='no_plot', action='store_true', default=False, help='Disable matplotlib plotting')
    parser.add_option('-m', '--msg', dest='msg', default='Hello, world!', help='Input message')
    parser.add_option('-s', '--snr', dest='snr_db', default=40.0, type=float, help='SNR in dB')
    parser.add_option('-b', '--baud', dest='baud', type=float, help='Baud rate')
    parser.add_option('-o', '--save-plot', dest='save_file', help='Save plot to image file')
    parser.add_option('-d', '--dropout', dest='dropout', help='Dropout signal from "start,end[,level]"')
    parser.add_option('-t', '--title', dest='title', help='Title for plot')
    parser.add_option('-f', '--figsize', dest='figsize', help='Figure size (w,h) in inches')
    parser.add_option('-x', '--x-range', dest='xrange', help='X-axis range (start,end)')
    parser.add_option('-l', '--label-names', dest='show_names', action='store_true', default=False, help='Show field names for text labels')
    parser.add_option('-a', '--no-annotation', dest='no_annotation', action='store_true', default=False, help='Disable plot annotation')
    
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

    if options.xrange is not None:
        options.xrange = [float(x) for x in options.xrange.split(',')]
        
    options.protocol = options.protocol.lower()

    print('** Ripyl demo **\n\n')

    if options.protocol in protocols:
        func = 'demo_' + options.protocol

        if options.protocol in ('usb-diff', 'hsic'):
            func = 'demo_usb'

        if options.protocol == 'j1850-pwm':
            func = 'demo_j1850_pwm'

        globals()[func](options) # Call the protocol demo routine
    else:
        print('Unrecognized protocol: "{}"'.format(options.protocol))
        sys.exit(1)


def demo_usb(options):
    import ripyl.protocol.usb as usb
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

    #bus_speed = usb.USBSpeed.HighSpeed
    #packets = [usb.USBSOFPacket(usb.USBPID.SOF, 0x12, bus_speed), \
    #    usb.USBTokenPacket(usb.USBPID.TokenOut, 0x6c, 0x2, bus_speed), \
    #    usb.USBHandshakePacket(usb.USBPID.ACK, bus_speed)]

    #packets = [usb.USBTokenPacket(usb.USBPID.TokenOut, 0x07, 0x01, bus_speed, delay=0.8e-7),
    #    usb.USBDataPacket(usb.USBPID.Data1, bytearray('Ripyl supports HSIC'), bus_speed),
    #    usb.USBHandshakePacket(usb.USBPID.ACK, bus_speed)]

    #packets = [usb.USBDataPacket(usb.USBPID.Data0, bytearray('Full'), usb.USBSpeed.FullSpeed),
    #    usb.USBHandshakePacket(usb.USBPID.PRE, usb.USBSpeed.FullSpeed),
    #    usb.USBDataPacket(usb.USBPID.Data1, bytearray('Low'), usb.USBSpeed.LowSpeed)]
    #packets[-1].swap_jk = True


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
        #samples, start_time, period = stream.extract_all_samples(nsy_dd)
        #samples = list(samples)
        #samples = samples[100:]
        #nsy_dd = list(stream.samples_to_sample_stream(samples, period, start_time))

        
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


    protocol_params = {
        'bus speed': usb.USBSpeed(bus_speed),
        'clock frequency': eng.eng_si(clock_freq, 'Hz')
    }

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'USB Simulation',
        'label_format': stream.AnnotationFormat.Text
    }


    report_results(records, packets, protocol_params, wave_params, decode_success, lambda d, o: (d.data, o))

    if options.protocol == 'usb':
        channels = OrderedDict([('D+ (V)', nsy_dp), ('D- (V)', nsy_dm)])
    elif options.protocol == 'usb-diff':
        channels = OrderedDict([('D+ - D- (V)', nsy_dd)])
    else: #HSIC
        channels = OrderedDict([('STROBE (V)', nsy_stb), ('DATA (V)', nsy_d)])
    plot_channels(channels, records, options, plot_params)


        
def demo_spi(options):
    import ripyl.protocol.spi as spi
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
    idle_start = 0.0

    #byte_msg = bytearray('SPI 1')
    #idle_start = 1.0e-6

    # Synthesize the waveform edge stream
    # This can be fed directly into spi_decode() if an analog waveform is not needed
    clk, data_io, cs = spi.spi_synth(byte_msg, word_size, clock_freq, cpol, cpha, idle_start=idle_start)

    #byte_msg = bytearray('SPI 2')
    #idle_start = 2.0e-6
    #clk2, data_io2, cs2 = spi.spi_synth(byte_msg, word_size, clock_freq, cpol, cpha, idle_start=idle_start)
    #clk = sigp.chain_edges(0.0, clk, clk2)
    #data_io = sigp.chain_edges(0.0, data_io, data_io2)
    #cs = sigp.chain_edges(0.0, cs, cs2)
    
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


    protocol_params = {
        'clock frequency': eng.eng_si(clock_freq, 'Hz'),
        'word size': word_size,
        'cpol': cpol,
        'cpha': cpha
    }

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'SPI Simulation',
        'label_format': stream.AnnotationFormat.Text
    }

    
    # Filter out StreamEvent objects
    data_records = [r for r in records if isinstance(r, stream.StreamSegment)]

    report_results(data_records, byte_msg, protocol_params, wave_params, decode_success, lambda d, o: (d.data, o))
    channels = OrderedDict([('CS (V)', nsy_cs), ('CLK (V)', nsy_clk), ('MOSI / MISO (V)', nsy_data_io)])
    plot_channels(channels, records, options, plot_params)



def demo_i2s(options):
    import ripyl.protocol.i2s as i2s
    print('I2S protocol\n')
    
    # I2S params
    audio_sample_rate = 5000 / 32.0 #44100
    word_size = 8
    frame_size = 16
    cpol = 0
    wspol = 0
    channels = 2

    clock_freq = audio_sample_rate * channels * frame_size
    
    # Sampled waveform params
    sample_rate = clock_freq * 100.0
    rise_time = min_rise_time(sample_rate) * 10.0 # 10x min. rise time
    noise_snr = options.snr_db
    
    #message = options.msg
    #byte_msg = bytearray(message.encode('latin1')) # Get raw bytes as integers
    samples = i2s.mono_to_stereo([0xA5, 1, 0xD1, 3,4, 0xC5])
    #samples = [0xA5, 1, 0xD1, 3,4, 0xCA, 0x55, 0x55]

    idle_start = 0.0
    idle_start = 1e-3
    idle_end = 1e-3

    # Synthesize the waveform edge stream
    # This can be fed directly into i2s_decode() if an analog waveform is not needed
    #clk, data_io, cs = spi.spi_synth(byte_msg, word_size, clock_freq, cpol, cpha, idle_start=idle_start)
    sck, sd, ws = i2s.i2s_synth(samples, word_size, frame_size, audio_sample_rate, \
        cpol, wspol, channels=channels, msb_justified=True, i2s_variant=i2s.I2SVariant.Standard, \
        data_offset=1, idle_start=idle_start, idle_end=idle_end)

    # Convert to a sample stream with band-limited edges and noise
    cln_sck_it = sigp.synth_wave(sck, sample_rate, rise_time)
    cln_sd_it = sigp.synth_wave(sd, sample_rate, rise_time)
    cln_ws_it = sigp.synth_wave(ws, sample_rate, rise_time)
    
    nsy_sck_it = sigp.amplify(sigp.noisify(cln_sck_it, snr_db=noise_snr), gain=3.3, offset=0.0)
    nsy_sd_it = sigp.amplify(sigp.noisify(cln_sd_it, snr_db=noise_snr), gain=3.3, offset=0.0)
    nsy_ws_it = sigp.amplify(sigp.noisify(cln_ws_it, snr_db=noise_snr), gain=3.3, offset=0.0)
    
    if options.dropout is not None:
        nsy_sd_it = sigp.dropout(nsy_sd_it, options.dropout[0], options.dropout[1], \
            options.dropout_level)
    
    # Capture the samples from the iterator
    nsy_sck = list(nsy_sck_it)
    nsy_sd = list(nsy_sd_it)
    nsy_ws = list(nsy_ws_it)
    
    # Decode the samples
    #decode_success = True
    decode_success = False
    records = []
    try:
        i2s.i2s_decode(iter(nsy_sck), iter(nsy_sd), iter(nsy_ws), word_size, frame_size, cpol, \
            wspol, channels=channels, data_offset=1)
        #records_it = spi.spi_decode(iter(nsy_clk), iter(nsy_data_io), iter(nsy_cs), cpol, cpha)
        #records = list(records_it)
        pass
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False


    protocol_params = {
        'clock frequency': eng.eng_si(clock_freq, 'Hz'),
        'word size': word_size,
        'frame_size': frame_size,
        'cpol': cpol,
        'wspol': wspol
    }

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'I2S Simulation',
        'label_format': stream.AnnotationFormat.Hex
    }

    
    # Filter out StreamEvent objects
    #data_records = [r for r in records if isinstance(r, stream.StreamSegment)]
    data_records = []

    #report_results(data_records, byte_msg, protocol_params, wave_params, decode_success, lambda d, o: (d.data, o))
    channels = OrderedDict([('SCK (V)', nsy_sck), ('WS (V)', nsy_ws), ('SD (V)', nsy_sd)])
    plot_channels(channels, records, options, plot_params)



def demo_i2c(options):
    import ripyl.protocol.i2c as i2c

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
    transfers.append(i2c.I2CTransfer(i2c.I2C.Read, 0x42, byte_msg))

    #transfers = [i2c.I2CTransfer(i2c.I2C.Write, 0x42, bytearray('I2C 1')), \
    #    i2c.I2CTransfer(i2c.I2C.Read, 0x42, bytearray('I2C 2'))]
    
    
    # Synthesize the waveform edge stream
    # This can be fed directly into i2c_decode() if an analog waveform is not needed
    scl, sda = i2c.i2c_synth(transfers, clock_freq, idle_start=3.0e-5, idle_end=3.0e-5)
    
    # Convert to a sample stream with band-limited edges and noise
    cln_scl_it = sigp.synth_wave(scl, sample_rate, rise_time, tau_factor=0.7)
    cln_sda_it = sigp.synth_wave(sda, sample_rate, rise_time, tau_factor=1.5)
    
    nsy_scl_it = sigp.amplify(sigp.noisify(cln_scl_it, snr_db=noise_snr), gain=3.3, offset=0.0)
    nsy_sda_it = sigp.amplify(sigp.noisify(cln_sda_it, snr_db=noise_snr), gain=3.3, offset=0.0)
    
    if options.dropout is not None:
        nsy_sda_it = sigp.dropout(nsy_sda_it, options.dropout[0], options.dropout[1], options.dropout_level)
    
    # Capture the samples from the iterator
    nsy_scl = list(nsy_scl_it)
    nsy_sda = list(nsy_sda_it)
    

    # Decode the samples
    decode_success = True
    try:
        records = list(i2c.i2c_decode(iter(nsy_scl), iter(nsy_sda)))
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False
        records = []

    protocol_params = {
        'clock frequency': eng.eng_si(clock_freq, 'Hz')
    }

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'I2C Simulation',
        'label_format': stream.AnnotationFormat.Text
    }

    data_records = list(i2c.reconstruct_i2c_transfers(records))
    
    report_results(data_records, transfers, protocol_params, wave_params, decode_success, lambda d, o: (d, o))
    channels = OrderedDict([('SCL (V)', nsy_scl), ('SDA (V)', nsy_sda)])
    plot_channels(channels, records, options, plot_params)


def demo_lm73(options):
    import ripyl.protocol.i2c as i2c
    import ripyl.protocol.lm73 as lm73

    print('LM73 protocol\n')
    
    # I2C params
    clock_freq = 100.0e3
    
    # Sampled waveform params
    sample_rate = clock_freq * 100.0
    rise_time = min_rise_time(sample_rate) * 10.0 # 10x min. rise time
    noise_snr = options.snr_db
    
    lm73_transfers = [
        lm73.LM73Transfer(0x48, lm73.LM73Operation.SetPointer, lm73.LM73Register.Identification),
        lm73.LM73Transfer(0x48, lm73.LM73Operation.ReadData, lm73.LM73Register.Identification, [0x01, 0x90]),
        lm73.LM73Transfer(0x48, lm73.LM73Operation.SetPointer, lm73.LM73Register.Temperature),
        lm73.LM73Transfer(0x48, lm73.LM73Operation.ReadData, lm73.LM73Register.Temperature, lm73.convert_temp(42.0)),
    ]

    i2c_transfers = [lm.i2c_tfer for lm in lm73_transfers]
    
    # Synthesize the waveform edge stream
    # This can be fed directly into i2c_decode() if an analog waveform is not needed
    scl, sda = i2c.i2c_synth(i2c_transfers, clock_freq, idle_start=3.0e-5, idle_end=3.0e-5)
    
    # Convert to a sample stream with band-limited edges and noise
    cln_scl_it = sigp.synth_wave(scl, sample_rate, rise_time, tau_factor=0.7)
    cln_sda_it = sigp.synth_wave(sda, sample_rate, rise_time, tau_factor=1.5)
    
    nsy_scl_it = sigp.amplify(sigp.noisify(cln_scl_it, snr_db=noise_snr), gain=3.3, offset=0.0)
    nsy_sda_it = sigp.amplify(sigp.noisify(cln_sda_it, snr_db=noise_snr), gain=3.3, offset=0.0)
    
    if options.dropout is not None:
        nsy_sda_it = sigp.dropout(nsy_sda_it, options.dropout[0], options.dropout[1], options.dropout_level)
    
    # Capture the samples from the iterator
    nsy_scl = list(nsy_scl_it)
    nsy_sda = list(nsy_sda_it)
    

    # Decode the samples
    decode_success = True
    try:
        records = list(i2c.i2c_decode(iter(nsy_scl), iter(nsy_sda)))
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False
        records = []

    protocol_params = {
        'clock frequency': eng.eng_si(clock_freq, 'Hz')
    }

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'LM73 Simulation',
        'label_format': stream.AnnotationFormat.Text,
        'ylim': (-0.5, 4.7)
    }

    i2c_records = list(i2c.reconstruct_i2c_transfers(records))
    lm73_records = list(lm73.lm73_decode(iter(i2c_records)))

    report_results(lm73_records, lm73_transfers, protocol_params, wave_params, decode_success, lambda d, o: (d, o))
    channels = OrderedDict([('SCL (V)', nsy_scl), ('SDA (V)', nsy_sda)])
    plot_channels(channels, lm73_records, options, plot_params)


def demo_uart(options):
    import ripyl.protocol.uart as uart

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

    #byte_msg = bytearray('UART 1')
    
    # Synthesize the waveform edge stream
    # This can be fed directly into uart_decode() if an analog waveform is not needed
    edges_it = uart.uart_synth(byte_msg, bits, baud, parity, stop_bits, idle_start=8.0 / baud, idle_end=8.0 / baud)

    #byte_msg = bytearray('UART 2')
    #edges2_it = uart.uart_synth(byte_msg, bits, baud, parity, stop_bits, idle_start=8.0 / baud, idle_end=8.0 / baud)
    #edges_it = sigp.chain_edges(0.0, edges_it, edges2_it)

    
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


    protocol_params = {
        'baud': baud,
        'decode baud': options.baud,
        'bits': bits,
        'parity': parity,
        'stop bits': stop_bits,
        'polarity': polarity
    }

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'UART Simulation',
        'label_format': stream.AnnotationFormat.Text
    }

    report_results(records, byte_msg, protocol_params, wave_params, decode_success, lambda d, o: (d.data, o))
    channels = OrderedDict([('Volts', noisy_samples)])
    plot_channels(channels, records, options, plot_params)



def demo_ps2(options):
    import ripyl.protocol.ps2 as ps2
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

    #byte_msg = bytearray('2hst 2dev')
    #direction = [ps2.PS2Dir.DeviceToHost]*4 + [ps2.PS2Dir.HostToDevice]*5
    frames = [ps2.PS2Frame(b, d) for b, d in zip(byte_msg, direction)]


    # Synthesize the waveform edge stream
    # This can be fed directly into spi_decode() if an analog waveform is not needed
    clk, data = ps2.ps2_synth(frames, clock_freq, 4 / clock_freq, 5 / clock_freq)
    
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

    protocol_params = {
        'clock frequency': eng.eng_si(clock_freq, 'Hz')
    }

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'PS/2 Simulation',
        'label_format': stream.AnnotationFormat.Text
    }


    report_results(records, frames, protocol_params, wave_params, decode_success, lambda d, o: (d.data, o))
    channels = OrderedDict([('CLK (V)', nsy_clk), ('DATA (V)', nsy_data)])
    plot_channels(channels, records, options, plot_params)


def demo_kline(options):
    import ripyl.protocol.iso_k_line as kline
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

    #messages = messages[0:2]


    
    # Synthesize the waveform edge stream
    # This can be fed directly into iso_k_line_decode() if an analog waveform is not needed
    edges_it = kline.iso_k_line_synth(messages, message_interval=8.0e-3, idle_start=8.0 / baud, idle_end=8.0 / baud)
    
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

    protocol_params = {
    }

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'ISO K-Line Simulation',
        'label_format': stream.AnnotationFormat.Hex
    }

    report_results(records, messages, protocol_params, wave_params, decode_success, lambda d, o: (d.msg.raw_data(full_message=True), o) )
    channels = OrderedDict([('Volts', noisy_samples)])
    plot_channels(channels, records, options, plot_params)



def demo_rc5(options):
    import ripyl.protocol.infrared.rc5 as rc5

    # Sampled waveform params
    carrier_freq = 36.0e3
    sample_rate = carrier_freq * 20.0
    rise_time = min_rise_time(sample_rate) * 4.0 # 4x min. rise time
    noise_snr = options.snr_db

    messages = [ \
        rc5.RC5Message(cmd=0x42, addr=0x14, toggle=0), \
        rc5.RC5Message(cmd=0x32, addr=0x1A, toggle=1)  \
    ]

    #messages = [messages[0]]

    # Synthesize the waveform edge stream
    edges = rc5.rc5_synth(messages, message_interval=5.0e-3, idle_start=1.0e-3, idle_end=1.0e-3)
    edges = ir.modulate(edges, carrier_freq, duty_cycle=0.3)

    noisy_samples = list(edges_to_waveform(edges, options, sample_rate, rise_time, 5.0, quant_full_range=10.0))

    # Decode the samples
    decode_success = True
    try:
        records = list(rc5.rc5_decode(iter(noisy_samples)))
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False
        records = []

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'RC5 Simulation',
        'label_format': stream.AnnotationFormat.Hex
    }

    report_results(records, messages, {}, wave_params, decode_success, lambda d, o: (d.data, o))
    channels = OrderedDict([('Volts', noisy_samples)])
    plot_channels(channels, records, options, plot_params)


def demo_rc6(options):
    import ripyl.protocol.infrared.rc6 as rc6

    # Sampled waveform params
    carrier_freq = 36.0e3
    sample_rate = carrier_freq * 20.0
    rise_time = min_rise_time(sample_rate) * 4.0 # 4x min. rise time
    noise_snr = options.snr_db

    messages = [ \
        rc6.RC6Message(cmd=0x42, addr=0x14, toggle=0, mode=0), \
        rc6.RC6Message(cmd=0x32, addr=0x1A, toggle=1, mode=1)  \
    ]

    #messages = [messages[0]]

    # Synthesize the waveform edge stream
    edges = rc6.rc6_synth(messages, message_interval=5.0e-3, idle_start=1.0e-3, idle_end=1.0e-3)
    edges = ir.modulate(edges, carrier_freq, duty_cycle=0.3)

    noisy_samples = list(edges_to_waveform(edges, options, sample_rate, rise_time, 5.0, quant_full_range=10.0))

    # Decode the samples
    decode_success = True
    try:
        records = list(rc6.rc6_decode(iter(noisy_samples)))
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False
        records = []

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'RC6 Simulation',
        'label_format': stream.AnnotationFormat.Hex
    }

    report_results(records, messages, {}, wave_params, decode_success, lambda d, o: (d.data, o))
    channels = OrderedDict([('Volts', noisy_samples)])
    plot_channels(channels, records, options, plot_params)


def demo_nec(options):
    import ripyl.protocol.infrared.nec as nec

    # Sampled waveform params
    carrier_freq = 38.0e3
    sample_rate = carrier_freq * 20.0
    rise_time = min_rise_time(sample_rate) * 4.0 # 4x min. rise time
    noise_snr = options.snr_db

    messages = [ \
        nec.NECMessage(cmd=0x42, addr_low=0x14), \
        nec.NECRepeat(), \
        nec.NECMessage(cmd=0x32, addr_low=0x1A)  \
    ]

    #messages = messages[0:2]

    # Synthesize the waveform edge stream
    edges = nec.nec_synth(messages, message_interval=5.0e-3, idle_start=1.0e-3, idle_end=1.0e-3)
    edges = ir.modulate(edges, carrier_freq, duty_cycle=0.3)

    noisy_samples = list(edges_to_waveform(edges, options, sample_rate, rise_time, 5.0, quant_full_range=10.0))

    # Decode the samples
    decode_success = True
    try:
        records = list(nec.nec_decode(iter(noisy_samples)))
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False
        records = []

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'NEC Simulation',
        'label_format': stream.AnnotationFormat.Hex
    }

    report_results(records, messages, {}, wave_params, decode_success, lambda d, o: (d.data, o))
    channels = OrderedDict([('Volts', noisy_samples)])
    plot_channels(channels, records, options, plot_params)




def demo_sirc(options):
    import ripyl.protocol.infrared.sirc as sirc

    # Sampled waveform params
    carrier_freq = 40.0e3
    sample_rate = carrier_freq * 20.0
    rise_time = min_rise_time(sample_rate) * 4.0 # 4x min. rise time
    noise_snr = options.snr_db

    messages = [ \
        sirc.SIRCMessage(cmd=0x42, device=0x14), \
        sirc.SIRCMessage(cmd=0x32, device=0x0A, extended=0x15)  \
    ]

    #messages = [messages[1]]

    # Synthesize the waveform edge stream
    edges = sirc.sirc_synth(messages, message_interval=5.0e-3, idle_start=1.0e-3, idle_end=1.0e-3)
    edges = ir.modulate(edges, carrier_freq, duty_cycle=0.3)

    noisy_samples = list(edges_to_waveform(edges, options, sample_rate, rise_time, 5.0, quant_full_range=10.0))

    # Decode the samples
    decode_success = True
    try:
        records = list(sirc.sirc_decode(iter(noisy_samples)))
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False
        records = []

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'SIRC Simulation',
        'label_format': stream.AnnotationFormat.Hex
    }

    report_results(records, messages, {}, wave_params, decode_success, lambda d, o: (d.data, o))
    channels = OrderedDict([('Volts', noisy_samples)])
    plot_channels(channels, records, options, plot_params)


def demo_can(options):
    import ripyl.protocol.can as can

    print('CAN protocol\n')
    
    # CAN params
    clock_freq = 100.0e3
    
    # Sampled waveform params
    sample_rate = clock_freq * 100.0
    rise_time = min_rise_time(sample_rate) * 10.0 # 10x min. rise time
    noise_snr = options.snr_db
    
    frames = [
        can.CANStandardFrame(0x42, [0x5A], None, None, False, trim_bits=2),
        can.CANErrorFrame(6, 0),
        can.CANExtendedFrame(0xececc9b, [0xDE, 0xAD], None, None, True),
    ]

    
    # Synthesize the waveform edge stream
    # This can be fed directly into i2c_decode() if an analog waveform is not needed
    ch, cl = can.can_synth(frames, clock_freq, idle_start=1.0e-5, idle_end=0.0e-5)
    
    # Convert to a sample stream with band-limited edges and noise
    cln_ch_it = sigp.synth_wave(ch, sample_rate, rise_time, tau_factor=1.5)
    cln_cl_it = sigp.synth_wave(cl, sample_rate, rise_time, tau_factor=1.5)
    
    nsy_ch_it = sigp.amplify(sigp.noisify(cln_ch_it, snr_db=noise_snr), gain=1.0, offset=2.5)
    nsy_cl_it = sigp.amplify(sigp.noisify(cln_cl_it, snr_db=noise_snr), gain=1.0, offset=1.5)
    
    if options.dropout is not None:
        nsy_cl_it = sigp.dropout(nsy_cl_it, options.dropout[0], options.dropout[1], options.dropout_level)
    
    # Capture the samples from the iterator
    nsy_ch = list(nsy_ch_it)
    nsy_cl = list(nsy_cl_it)
    

    # Decode the samples
    decode_success = True
    bit_timing = can.CANTiming(1, 4, resync_jump_quanta=2)
    try:
        records = list(can.can_decode(iter(nsy_cl), bit_timing=bit_timing))
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False
        records = []

    print('%%%% records:', len(records))
    for r in records:
        print('  ', r.data)

    protocol_params = {
        'clock frequency': eng.eng_si(clock_freq, 'Hz')
    }

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'CAN Simulation',
        'label_format': stream.AnnotationFormat.Text,
        'ylim': (1.0, 4.0)
    }

    report_results(records, frames, protocol_params, wave_params, decode_success, lambda d, o: (d.data, o))
    channels = OrderedDict([('CH (V)', nsy_ch), ('CL (V)', nsy_cl)])
    plot_channels(channels, records, options, plot_params)


def demo_lin(options):
    import ripyl.protocol.lin as lin
    print('ISO LIN protocol\n')
    
    # LIN params
    baud = 10400

    # Sampled waveform params
    sample_rate = baud * 100.0
    rise_time = min_rise_time(sample_rate) * 10.0 # 10x min. rise time
    noise_snr = options.snr_db

    frames = [
        lin.LINFrame(0x3A, [0x8B, 0xAD, 0xF0, 0x0D], cs_type=lin.LINChecksum.Enhanced),
        lin.LINFrame(0x29, []),
        #lin.LINFrame(0x29, [6,7])
    ]

    # Synthesize the waveform edge stream
    edges_it = lin.lin_synth(frames, baud, frame_interval=10.0 / baud, idle_start=4.0 / baud, \
                            idle_end=8.0 / baud, byte_interval=3.0 / baud)
    
    # Convert to a sample stream with band-limited edges and noise
    clean_samples_it = sigp.synth_wave(edges_it, sample_rate, rise_time, tau_factor=1.0)
    
    noisy_samples_it = sigp.quantize(sigp.amplify(sigp.noisify(clean_samples_it, snr_db=noise_snr), gain=12.0), 50.0)
    if options.dropout is not None:
        noisy_samples_it = sigp.dropout(noisy_samples_it, options.dropout[0], options.dropout[1], options.dropout_level)
    
    # Capture the samples from the iterator
    noisy_samples = list(noisy_samples_it)
    

    # Decode the samples
    decode_success = True
    records = []
    try:
        records_it = lin.lin_decode(iter(noisy_samples))
        records = list(records_it)
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False

    protocol_params = {
        'baud': baud
    }

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'LIN Simulation',
        'label_format': stream.AnnotationFormat.Hex
    }

    report_results(records, frames, protocol_params, wave_params, decode_success, lambda d, o: (d.data, o) )
    channels = OrderedDict([('Volts', noisy_samples)])
    plot_channels(channels, records, options, plot_params)



def demo_ethernet(options):
    import ripyl.protocol.ethernet as ether
    print('Ethernet protocol\n')
    
    # Ethernet params
    bit_rate = 10.0e6

    # Sampled waveform params
    sample_rate = bit_rate * 20.0
    #rise_time = min_rise_time(sample_rate) * 10.0 # 10x min. rise time
    rise_time = 1.0 / 80.0e6
    noise_snr = options.snr_db

    frames = [
        ether.EthernetFrame('2:2:3:4:5:6', 'a:b:c:d:e:f', range(66), length_type=0x800 ),
        #ether.EthernetLinkTest(ether.EthernetLinkCode(1,1,1,1,1)),
        ether.EthernetFrame('1:2:3:4:5:6', 'a:b:c:d:e:f', range(67), tags=[ether.EthernetTag(0x8100, 1),
                ether.EthernetTag(0x9100, 2)], length_type=0x800)
    ]

    # Synthesize the waveform edge stream
    edges_it = ether.ethernet_synth(frames, overshoot=(0.75, 0.25), idle_start=2.0e-6, \
                                    frame_interval=(12 * 8 * 100.0e-9), idle_end=2.0e-6)

    
    # Convert to a sample stream with band-limited edges and noise
    clean_samples_it = sigp.synth_wave(edges_it, sample_rate, rise_time, tau_factor=0.5)
    
    noisy_samples_it = sigp.quantize(sigp.amplify(sigp.noisify(clean_samples_it, snr_db=noise_snr), gain=1.0), 8.0)
    if options.dropout is not None:
        noisy_samples_it = sigp.dropout(noisy_samples_it, options.dropout[0], options.dropout[1], options.dropout_level)
    
    # Capture the samples from the iterator
    noisy_samples = list(noisy_samples_it)


    #ether_samples, sample_period, start_time = tsup.read_bin_file('test/data/ether_10bt_39.bin')
    #ether_it = stream.samples_to_sample_stream(ether_samples, sample_period, start_time)
    #noisy_samples = list(ether_it)
    

    # Decode the samples
    decode_success = True
    records = []
    try:
        records_it = ether.ethernet_decode(iter(noisy_samples))
        records = list(records_it)
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False

    protocol_params = {
        'bit_rate': bit_rate
    }

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'Ethernet Simulation',
        'label_format': stream.AnnotationFormat.Hex
    }

    report_results(records, frames, protocol_params, wave_params, decode_success, lambda d, o: (d.data, o) )
    channels = OrderedDict([('Volts', noisy_samples)])
    plot_channels(channels, records, options, plot_params)


def demo_j1850(options):
    import ripyl.protocol.j1850 as j1850
    print('J1850 VPW protocol\n')

    bit_rate = 10400
    
    # Sampled waveform params
    sample_rate = bit_rate * 40.0
    rise_time = min_rise_time(sample_rate) * 10.0 # 10x min. rise time
    noise_snr = options.snr_db

    frames = [
        j1850.J1850Frame(3, j1850.J1850MT.FunctionCmd, [0x01, 0x00], 0x6a, 0xf1),
        j1850.J1850Break(),
        j1850.J1850Frame(3, j1850.J1850MT.FunctionCmd, [0xBE, 0x1E, 0x90, 0x11], 0x6b, 0xd1)
    ]

    #norm_bit = j1850.VPWNormBitStyle.SAE
    norm_bit = j1850.VPWNormBitStyle.GM

    # Synthesize the waveform edge stream
    breaks = None # [(0, 0.2)]
    edges_it = j1850.j1850_vpw_synth(frames, norm_bit=norm_bit, breaks=breaks, idle_start=2.0e-4, \
                                    frame_interval=1.0e-3)

    # Convert to a sample stream with band-limited edges and noise
    clean_samples_it = sigp.synth_wave(edges_it, sample_rate, rise_time, tau_factor=0.5)
    
    noisy_samples_it = sigp.quantize(sigp.amplify(sigp.noisify(clean_samples_it, snr_db=noise_snr), gain=7.0), 16.0)
    if options.dropout is not None:
        noisy_samples_it = sigp.dropout(noisy_samples_it, options.dropout[0], options.dropout[1], options.dropout_level)
    
    # Capture the samples from the iterator
    noisy_samples = list(noisy_samples_it)
    

    # Decode the samples
    decode_success = True
    records = []
    try:
        records_it = j1850.j1850_vpw_decode(iter(noisy_samples), norm_bit=norm_bit)
        records = list(records_it)

    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False

    protocol_params = {
        'bit_rate': bit_rate
    }

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'J1850 VPW Simulation',
        'label_format': stream.AnnotationFormat.Hex
    }

    report_results(records, frames, protocol_params, wave_params, decode_success, lambda d, o: (d.data, o) )
    channels = OrderedDict([('Volts', noisy_samples)])
    plot_channels(channels, records, options, plot_params)


def demo_j1850_pwm(options):
    import ripyl.protocol.j1850 as j1850
    print('J1850 PWM protocol\n')

    bit_rate = 41600
    
    # Sampled waveform params
    sample_rate = bit_rate * 40.0
    rise_time = min_rise_time(sample_rate) * 5.0 # 10x min. rise time
    noise_snr = options.snr_db

    frames = [
        j1850.J1850Frame(3, j1850.J1850MT.Function, [0x01, 0x00], 0x6a, 0xf1, [0xd1]),
        j1850.J1850Frame(3, j1850.J1850MT.Broadcast, [0xBE, 0x1E, 0x90, 0x11], 0x6b, 0xd1, [0xf1])
    ]

    # Synthesize the waveform edge stream
    breaks = None #[(0, 0.2)]
    p, m = j1850.j1850_pwm_synth(frames, breaks=breaks, idle_start=50.0e-6, \
                                    frame_interval=(12 * 8 * 100.0e-9), idle_end=2.0e-6)

    # Convert to a sample stream with band-limited edges and noise
    clean_p_it = sigp.synth_wave(p, sample_rate, rise_time, tau_factor=0.1)
    clean_m_it = sigp.synth_wave(m, sample_rate, rise_time, tau_factor=0.1)
    
    noisy_p_it = sigp.quantize(sigp.amplify(sigp.noisify(clean_p_it, snr_db=noise_snr), gain=5.0), 8.0)
    noisy_m_it = sigp.quantize(sigp.amplify(sigp.noisify(clean_m_it, snr_db=noise_snr), gain=5.0), 8.0)
    if options.dropout is not None:
        noisy_p_it = sigp.dropout(noisy_p_it, options.dropout[0], options.dropout[1], options.dropout_level)
        noisy_m_it = sigp.dropout(noisy_m_it, options.dropout[0], options.dropout[1], options.dropout_level)
    
    # Capture the samples from the iterator
    noisy_p = list(noisy_p_it)
    noisy_m = list(noisy_m_it)


    #dp_samples, sample_period, start_time = tsup.read_bin_file('test/data/j1850_1p.bin')
    #dp_it = stream.samples_to_sample_stream(dp_samples, sample_period, start_time)
    #dm_samples, sample_period, start_time = tsup.read_bin_file('test/data/j1850_1m.bin')
    #dm_it = stream.samples_to_sample_stream(dm_samples, sample_period, start_time)
    #noisy_p = list(dm_it)
    #noisy_m = list(dp_it)
    

    # Decode the samples
    decode_success = True
    records = []
    try:
        records_it = j1850.j1850_pwm_decode(iter(noisy_p))
        records = list(records_it)
        
    except stream.StreamError as e:
        print('Decode failed:\n  {}'.format(e))
        decode_success = False

    protocol_params = {
        'bit_rate': bit_rate
    }

    wave_params = {
        'sample rate': eng.eng_si(sample_rate, 'Hz'),
        'rise time': eng.eng_si(rise_time, 's', 1),
        'SNR': str(options.snr_db) + ' dB'
    }

    plot_params = {
        'default_title': 'J1850 PWM Simulation',
        'label_format': stream.AnnotationFormat.Hex
    }

    report_results(records, frames, protocol_params, wave_params, decode_success, lambda d, o: (d.data, o) )
    channels = OrderedDict([('Bus-(V)', noisy_m), ('Bus+(V)', noisy_p)])
    plot_channels(channels, records, options, plot_params)




def edges_to_waveform(edges, options, sample_rate, rise_time, gain, offset=0.0, quant_full_range=20.0):
    # Convert to a sample stream with band-limited edges and noise
    clean_samples = sigp.synth_wave(edges, sample_rate, rise_time)

    noisy_samples = sigp.quantize(sigp.amplify(sigp.noisify(clean_samples, options.snr_db), gain=gain, \
        offset=offset), quant_full_range)

    if options.dropout is not None:
        noisy_samples = sigp.dropout(noisy_samples, options.dropout[0], options.dropout[1], options.dropout_level)

    return noisy_samples


def plot_channels(channels, annotations, options, plot_params, sample_points=None):
    if not options.no_plot:
        if options.title is not None:
            title = options.title
        else:
            title = plot_params['default_title']

        if 'ylim' in plot_params:
            ylim = plot_params['ylim']
        else:
            ylim = None

        if options.xrange is not None:
            xlim = options.xrange
        else:
            xlim = None


        plotter = rplot.Plotter()
        annotations = None if options.no_annotation else annotations
        plotter.plot(channels, annotations, title, label_format=plot_params['label_format'], show_names=options.show_names, \
            ylim=ylim, xlim=xlim)

        if sample_points is not None:
            # Each sample point is a pair with the first element being the start of the bit
            # and the second is the sample point
            #print('### plotting sample points', len(sample_points))
            sp_height = [2.0] * len(sample_points)
            sample_times = [sp[1] for sp in sample_points]
            plotter.axes[-1].plot(sample_times, sp_height, color='r', marker='o')

            sp_height = [1.7] * len(sample_points)
            sample_times = [sp[0] for sp in sample_points]
            plotter.axes[-1].plot(sample_times, sp_height, color='b', marker='o')


        if options.save_file is None:
            plotter.show()
        else:
            plotter.save_plot(options.save_file, options.figsize)

def report_results(decoded_recs, orig_messages, protocol_params, wave_params, decode_success, extract_func=None):

    # Report results
    print('\nProtocol parameters:')
    print('  Messages:')
    for msg in orig_messages:
        print(note('   {}'.format(msg)))
    for k, v in protocol_params.iteritems():
        print(note('  {}: {}'.format(k, v)))

    print('Waveform parameters:')
    for k, v in wave_params.iteritems():
        print(note('  {}: {}'.format(k, v)))


    if decode_success and extract_func is not None:
        print('\nDecoded messages:')
        msg_match = True

        for dmsg, omsg in [extract_func(d, o) for d, o in zip(decoded_recs, orig_messages)]:
            if dmsg != omsg:
                msg_match = False
                #m_flag =  ' < MISMATCH'
                msg = error('  {} < MISMATCH'.format(dmsg))
            else:
                #m_flag = ''
                msg = note('  {}'.format(dmsg))

            print(msg)
            #print('  {}{}'.format(dmsg, m_flag))

        if msg_match:
            print(success('  (matches input message)'))
        else:
            print(error('  (MISMATCH to input message)'))


        
if __name__ == '__main__':
    main()
