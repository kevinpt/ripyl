#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Ripyl protocol decode library
   USB protocol decoder
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

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import string

import ripyl.streaming as stream

def waveform_bounds(raw_samples):
    max_wf = max(raw_samples)
    min_wf = min(raw_samples)
    span = max_wf - min_wf
    
    # Overlay bounds
    ovl_top = max_wf + span * 0.15
    ovl_bot = min_wf - span * 0.05
    
    # Inset overlay bounds
    i_ovl_top = max_wf + span * 0.01
    i_ovl_bot = min_wf - span * 0.01
    
    bounds = {
        'max': max_wf,
        'min': min_wf,
        'ovl_top': ovl_top,
        'ovl_bot': ovl_bot,
        'i_ovl_top': i_ovl_top,
        'i_ovl_bot': i_ovl_bot
    }
    
    return bounds

def plot(channels, records, title='', label_format='text', save_file=None):
    '''Generic plot function
    
    Dispatches to the protocol specific plotters based on the keys in the channels dict
    
    '''
    
    try:
        keys = channels.keys()
        if 'dp' in keys and 'dm' in keys:
            return usb_plot(channels, records, title, label_format, save_file)
        elif 'clk' in keys and ('data_io' in keys or 'miso' in keys or 'mosi' in keys):
            return spi_plot(channels, records, title, label_format, save_file)
        elif 'scl' in keys and 'sda' in keys:
            return i2c_plot(channels, records, title, label_format, save_file)
        elif len(keys) == 1:
            return usb_plot(channels, records, title, label_format, save_file)
        
    except AttributeError:
        return uart_plot(channels, records, title, label_format, save_file)
    
    
def usb_plot(channels, records, title='', label_format='text', save_file=None):
    import ripyl.protocol.usb as usb
    from ripyl.util.bitops import join_bits

    if len(channels.keys()) == 1:
        diff_usb = True
        dm = channels[channels.keys()[0]]
        
        dm_t, dm_wf = zip(*dm)
        dm_b = waveform_bounds(dm_wf)
    
        text_ypos = (dm_b['max'] + dm_b['ovl_top']) / 2.0

        fig, ax1 = plt.subplots(1, 1)

        ax1.plot(dm_t, dm_wf)
        ax1.set_title(title)

        ax1.set_xlabel('Time (s)')
        ax1.set_ylabel('D+ - D- (V)')
        
        ann_ax = ax1
        
    else:
        diff_usb = False
        dp = channels['dp']
        dm = channels['dm']
        dp_t, dp_wf = zip(*dp)
        dm_t, dm_wf = zip(*dm)
    
        #dp_b = waveform_bounds(dp_wf)
        dm_b = waveform_bounds(dm_wf)
    
        text_ypos = (dm_b['max'] + dm_b['ovl_top']) / 2.0

        fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, sharey=True)

        ax1.plot(dp_t, dp_wf, color='green')
        ax1.set_ylabel('D+ (V)')
        ax1.set_title(title)
        
        ax2.plot(dm_t, dm_wf)
        ax2.set_xlabel('Time (s)')
        ax2.set_ylabel('D- (V)')
        
        ann_ax = ax2
    
    for r in records:
        if not (r.kind == 'USB packet'):
            continue
            
        # Packet frame rectangle
        f_start = r.start_time
        f_end = r.end_time
        f_rect = patches.Rectangle((f_start, dm_b['ovl_bot']), width=f_end - f_start, \
            height=dm_b['ovl_top'] - dm_b['ovl_bot'], facecolor='orange', alpha=0.2)
        ann_ax.add_patch(f_rect)
        
        offsets = r.field_offsets()
        
        # PID rectangle
        p_start = offsets['PID'][0]
        p_end = offsets['PID'][1]
        p_rect = patches.Rectangle((p_start, dm_b['i_ovl_bot']), width=p_end - p_start, \
            height=dm_b['i_ovl_top'] - dm_b['i_ovl_bot'], facecolor='red', alpha=0.3)
        ann_ax.add_patch(p_rect)
        ann_ax.text((p_start + p_end) / 2.0, text_ypos, usb.USBPID(r.packet.pid), \
            size='small', ha='center', color='black')
        
        used_fields = ['PID']
        
        c_start = -1
        if 'CRC5' in offsets:
            c_start = offsets['CRC5'][0]
            c_end = offsets['CRC5'][1]
            used_fields.append('CRC5')
        elif 'CRC16' in offsets:
            c_start = offsets['CRC16'][0]
            c_end = offsets['CRC16'][1]
            used_fields.append('CRC16')
            
        if c_start > 0.0:
            c_rect = patches.Rectangle((c_start, dm_b['i_ovl_bot']), width=c_end - c_start, \
                height=dm_b['i_ovl_top'] - dm_b['i_ovl_bot'], facecolor='yellow', alpha=0.3)
            ann_ax.add_patch(c_rect)
            
            crc = join_bits(r.crc)
            ann_ax.text((c_start + c_end) / 2.0, text_ypos, hex(crc), \
                size='small', ha='center', color='black')
            
        # Draw the remaining fields
        unused_fields = [k for k in offsets.keys() if k not in used_fields]
        # Sort them in time order
        unused_fields = sorted(unused_fields, key=lambda f: offsets[f][0])

        colors = ['blue', 'green']
        color_ix = 1
        for field in unused_fields:
            start, end = offsets[field]
            d_start = start
            d_end = end
            color_ix = 1 - color_ix
            color = colors[color_ix]
            d_rect = patches.Rectangle((d_start, dm_b['i_ovl_bot']), width=d_end - d_start, \
                height=dm_b['i_ovl_top'] - dm_b['i_ovl_bot'], facecolor=color, alpha=0.3)
            ann_ax.add_patch(d_rect)
        
        if 'Data' in offsets.keys():
            chars = []
            for b in r.packet.data:
                if chr(b) in string.printable:
                    chars.append(chr(b))
                else:
                    chars.append('({})'.format(hex(b)[2:]))
            
        
            #decoded_msg = ''.join([chr(b) for b in r.packet.data])
            decoded_msg = ''.join(chars)
            d_start = offsets['Data'][0]
            d_end = offsets['Data'][1]
            ann_ax.text((d_start + d_end) / 2.0, text_ypos, decoded_msg, \
                size='small', ha='center', color='black', weight='bold')            

    ann_ax.set_ylim(dm_b['ovl_bot'] * 1.05, dm_b['ovl_top'] * 1.05)
    
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.12)
    if save_file is None:
        plt.show()
    else:
        print('Writing plot to file:', save_file)
        plt.savefig(fname)


def spi_plot(channels, records, title='', label_format='text', save_file=None):
    clk = channels['clk']
    data_io = channels['data_io']
    cs = channels['cs']
    clk_t, clk_wf = zip(*clk)
    data_io_t, data_io_wf = zip(*data_io)
    cs_t, cs_wf = zip(*cs)
    
    clk_b = waveform_bounds(clk_wf)
    data_io_b = waveform_bounds(data_io_wf)
    cs_b = waveform_bounds(cs_wf)
    
    text_ypos = (data_io_b['max'] + data_io_b['ovl_top']) / 2.0

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, sharex=True, sharey=True)

    ax1.plot(cs_t, cs_wf, color='red')
    ax1.set_ylabel('CS (V)')
    ax1.set_title(title)
    
    ax2.plot(clk_t, clk_wf, color='green')
    ax2.set_ylabel('CLK (V)')
    
    ax3.plot(data_io_t, data_io_wf)
    ax3.set_xlabel('Time (s)')
    ax3.set_ylabel('MOSI / MISO (V)')
    
    for r in records:
        if not (r.kind == 'SPI frame'):
            continue
            
        # Frame rectangle
        f_start = r.start_time
        f_end = r.end_time
        f_rect = patches.Rectangle((f_start, data_io_b['ovl_bot']), width=f_end - f_start, \
            height=data_io_b['ovl_top'] - data_io_b['ovl_bot'], facecolor='orange', alpha=0.2)
        ax3.add_patch(f_rect)
        
        color = 'black'
        angle = 'horizontal'
        if label_format == 'text':
            char = chr(r.data)
            if char not in string.printable:
                char = hex(r.data)
                color='red'
                angle = 45

        elif label_format == 'hex':
            char = hex(r.data)
            angle = 45
        else:
            raise ValueError('Unrecognized label format: "{}"'.format(label_format))

        ax3.text((r.start_time + r.end_time) / 2.0, text_ypos, char, \
            size='large', ha='center', color=color, rotation=angle)


    ax3.set_ylim(data_io_b['ovl_bot'] * 1.05, data_io_b['ovl_top'] * 1.05)

    plt.tight_layout()
    plt.subplots_adjust(bottom=0.12)
    if save_file is None:
        plt.show()
    else:
        print('Writing plot to file:', save_file)
        plt.savefig(fname)



def i2c_plot(channels, records, title='', label_format='text', save_file=None):
    scl = channels['scl']
    sda = channels['sda']
    scl_t, scl_wf = zip(*scl)
    sda_t, sda_wf = zip(*sda)
    
    scl_b = waveform_bounds(scl_wf)
    sda_b = waveform_bounds(sda_wf)
    
    text_ypos = (sda_b['max'] + sda_b['ovl_top']) / 2.0

    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, sharey=True)

    ax1.plot(scl_t, scl_wf, color='green')
    ax1.set_ylabel('SCL (V)')
    ax1.set_title(title)
    
    ax2.plot(sda_t, sda_wf)
    ax2.set_xlabel('Time (s)')
    ax2.set_ylabel('SDA (V)')
    
    for r in records:
        if not (r.kind == 'I2C byte' or r.kind == 'I2C address'):
            continue
            
        # There are 9-bits in every byte so we can infer the clock period
        if len(r.subrecords) == 0:
            clock_period = (r.end_time - r.start_time) / 9.0
            byte_set = [r]
        else:
            clock_period = (r.subrecords[0].end_time - r.subrecords[0].start_time) / 9.0
            byte_set = r.subrecords
            
        # Frame rectangle
        f_start = r.start_time - 0.4 * clock_period
        f_end = r.end_time + 0.4 * clock_period
        f_rect = patches.Rectangle((f_start, sda_b['ovl_bot']), width=f_end - f_start, \
            height=sda_b['ovl_top'] - sda_b['ovl_bot'], facecolor='orange', alpha=0.2)
        ax2.add_patch(f_rect)

        for b in byte_set:
        
            # Ack bit rectangle
            ack_start = b.end_time - 0.25 * clock_period
            ack_end = b.end_time + 0.25 * clock_period
            # try:
            ack_bit = b.ack_bit
            # except AttributeError:
                # ack_bit = r.subrecords[0].ack_bit
            color = 'yellow' if ack_bit == 0 else 'red'
            a_rect = patches.Rectangle((ack_start, sda_b['i_ovl_bot']), width=ack_end - ack_start, \
                height=sda_b['i_ovl_top'] - sda_b['i_ovl_bot'], facecolor=color, alpha=0.3)
            ax2.add_patch(a_rect)

            # Data bits rectangle
            d_start = b.start_time - 0.25 * clock_period
            d_end = d_start + 8.5 * clock_period
            d_rect = patches.Rectangle((d_start, sda_b['i_ovl_bot']), width=d_end - d_start, \
                height=sda_b['i_ovl_top'] - sda_b['i_ovl_bot'], facecolor='blue', alpha=0.3)
            ax2.add_patch(d_rect)

        color = 'black'
        angle = 'horizontal'
        if label_format == 'text':
            if r.kind != 'I2C address':
                char = chr(r.data)
                if char not in string.printable:
                    char = hex(r.data)
                    color='red'
                    angle = 45
            else: # an address
                char = hex(r.data) + (' r' if r.r_wn else ' w')
                angle = 45
        elif label_format == 'hex':
            char = hex(r.data)
            angle = 45
        else:
            raise ValueError('Unrecognized label format: "{}"'.format(label_format))

        ax2.text((r.start_time + r.end_time) / 2.0, text_ypos, char, \
            size='large', ha='center', color=color, rotation=angle)


    ax2.set_ylim(sda_b['ovl_bot'] * 1.05, sda_b['ovl_top'] * 1.05)

    plt.tight_layout()
    plt.subplots_adjust(bottom=0.12)
    if save_file is None:
        plt.show()
    else:
        print('Writing plot to file:', save_file)
        plt.savefig(fname)


def uart_plot(samples, records, title='', label_format='text', save_file=None):

    t, wf = zip(*samples)
    
    max_wf = max(wf)
    min_wf = min(wf)
    span = max_wf - min_wf
    
    # Overlay bounds
    ovl_top = max_wf + span * 0.15
    ovl_bot = min_wf - span * 0.05
    
    # Inset overlay bounds
    i_ovl_top = max_wf + span * 0.01
    i_ovl_bot = min_wf - span * 0.01
    
    text_ypos = (max_wf + ovl_top) / 2.0
    
    ax = plt.axes()
    
    plt.xlabel('Time (s)')
    plt.ylabel('Volts')
    plt.title(title)
    
    for r in records:
        # Frame rectangle
        r_rect = patches.Rectangle((r.start_time, ovl_bot), width=r.end_time - r.start_time, \
            height=ovl_top - ovl_bot, facecolor='orange', alpha=0.2)
        ax.add_patch(r_rect)
        
        # Data bits rectangle
        d_sr = [sr for sr in r.subrecords if sr.kind == 'data bits'][0]
        d_rect = patches.Rectangle((d_sr.start_time, i_ovl_bot), width=d_sr.end_time - d_sr.start_time, \
            height=i_ovl_top - i_ovl_bot, facecolor='blue', alpha=0.2)
        ax.add_patch(d_rect)
        
        # Try to find any parity bit
        p_sr = [sr for sr in r.subrecords if sr.kind == 'parity']
        if len(p_sr) > 0:
            p_sr = p_sr[0]
            color = 'yellow' if p_sr.status < stream.StreamStatus.Error else 'red'
            p_rect = patches.Rectangle((p_sr.start_time, i_ovl_bot), width=p_sr.end_time - p_sr.start_time, \
                height=i_ovl_top - i_ovl_bot, facecolor=color, alpha=0.3)
            ax.add_patch(p_rect)

        color = 'black'
        angle = 'horizontal'
        if label_format == 'text':
            char = str(r)
            if char not in string.printable:
                char = hex(r.data)
                color='red'
                angle = 45
        elif label_format == 'hex':
            char = hex(r.data)
            angle = 45
        else:
            raise ValueError('Unrecognized label format: "{}"'.format(label_format))

        plt.text((r.start_time + r.end_time) / 2.0, text_ypos, char, \
            size='large', ha='center', color=color, rotation=angle)

    # Plot the waveform
    plt.plot(t, wf)
    plt.ylim(ovl_bot * 1.05, ovl_top * 1.05)

    plt.tight_layout()
    plt.subplots_adjust(bottom=0.12)
    if save_file is None:
        plt.show()
    else:
        print('Writing plot to file:', save_file)
        plt.savefig(fname)