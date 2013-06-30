#!/usr/bin/python
# -*- coding: utf-8 -*-

'''USB transaction decoder
   
   Processes a USB packet stream into a set of USBTransaction objects
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

from ripyl.streaming import *
import ripyl.protocol.usb as usb

class USBTransaction(StreamRecord):
    '''Collection of packets forming a USB transaction
    
    The 'subrecords' attribute is aliased to the 'packets' attribute.
    These "packets" are USBStreamPacket objects.
    
    '''
    def __init__(self, packets, status=StreamStatus.Ok):
        '''
        packets
            A sequence of USBStreamPacket objects
        '''
        StreamRecord.__init__(self, kind='USB transaction', status=status)
        self.subrecords = packets
        
    @property
    def packets(self):
        return self.subrecords
    
    @packets.setter
    def packets(self, value):
        self.subrecords = value

    @property
    def start_time(self):
        if len(self.packets) > 0:
            return self.packets[0].start_time
        else:
            return None

    @property
    def end_time(self):
        if len(self.packets) > 0:
            return self.packets[-1].end_time
        else:
            return None
            
    def __eq__(self, other):
        if not hasattr(other, 'packets'):
            return False

        if len(self.packets) != len(other.packets):
            return False

        match = True
        for sp, op in zip(self.packets, other.packets):
            if sp.packet != op.packet:
                match = False
                break
                
        return match
            
    def __ne__(self, other):
        return not self == other


def usb_transactions_decode(records):
    '''Convert a stream of USB packets into transactions
    
    records
        An iterator containing USBPacket objects as produced by usb.usb_decode()
        
    Yields a stream of USBTransaction objects containing packets merged into identifiable
      transactions. Any non-USBPacket objects in the input stream will also be present as
      will SOF packets.
    '''

    # These are keyed by the (addr, endp) as a tuple
    trans_buf = {}

    # Invalid address and endpoint used for partial transaction packets at start of acquisition
    init_key = (-1, -1)
    prev_key = init_key
    prefix_pkt = None
    for rec in records:
        if rec.kind != 'USB packet':
            yield rec
            continue
            
        pkt = rec.packet
        # Attempt to get the addr and endp fields
        try:
            key = (pkt.addr, pkt.endp)
            
            # IN and OUT endpoints are logically separate except for endpoint 0
            # Modify the key to make them unique
            if pkt.endp > 0 and (pkt.pid == usb.USBPID.TokenIn or pkt.pid == usb.USBPID.PING):
                key = (pkt.addr, pkt.endp + 16)
                
        except AttributeError:
            # The packet doesn't have both addr and endp
            key = prev_key
            
            if pkt.pid == usb.USBPID.SOF:
                yield rec
                continue
            elif pkt.pid == usb.USBPID.SPLIT or (pkt.pid == usb.USBPID.PRE and rec.speed != usb.USBSpeed.HighSpeed):
                prefix_pkt = rec # Save it until we have a packet with a proper key
                continue


        if key in trans_buf:
            # If the new packet is a token we either lost a packet or a handshake was not needed to terminate
            # the previous transaction.
            
            # In any case yield the current packets accumulated for the key and start a new transaction
            token_pids =(usb.USBPID.TokenOut, usb.USBPID.TokenIn, usb.USBPID.TokenSetup, usb.USBPID.PING, \
                usb.USBPID.EXT)
            if pkt.pid in token_pids:
                # First yield any initial partial packets waiting in the dict
                if init_key in trans_buf and key != init_key:
                    yield USBTransaction(trans_buf[init_key])
                    del trans_buf[init_key]
                    
                yield USBTransaction(trans_buf[key])
                trans_buf[key] = []

            if prefix_pkt is not None:
                trans_buf[key].append(prefix_pkt)
                prefix_pkt = None

            # Add the packet to the transaction
            trans_buf[key].append(rec)
        else:
            # Start a new transaction
            trans_buf[key] = []
            
            if prefix_pkt is not None:
                trans_buf[key].append(prefix_pkt)
                prefix_pkt = None

            trans_buf[key].append(rec)

        # Most transactions end in a handshake packet except for isochronous and split
        hshake_pids = (usb.USBPID.ACK, usb.USBPID.NAK, usb.USBPID.STALL, usb.USBPID.NYET)
        if pkt.pid in hshake_pids or (pkt.pid == usb.USBPID.ERR and rec.speed == usb.USBSpeed.HighSpeed):

            # First yield any initial partial packets waiting in the dict
            if init_key in trans_buf and key != init_key:
                yield USBTransaction(trans_buf[init_key])
                del trans_buf[init_key]

            yield USBTransaction(trans_buf[key])
            del trans_buf[key]

        
        prev_key = key

    # yield any remaining transactions
    for key, pkts in sorted(trans_buf.items()):
        yield USBTransaction(pkts)


def extract_transaction_packets(records):
    '''Convert a stream of USB transactions into raw USBPacket objects

    records
        Iterator of USBTransaction objects
        
    Yields a stream of USBPacket objects
    '''
    for rec in records:
        # SOF packets aren't merged into any transaction object
        if rec.kind == 'USB packet':
            yield rec.packet
            continue
    
        # The stream could contain USBError records. Just pass them through
        if rec.kind != 'USB transaction':
            yield rec
            continue

        # This is a USBTransaction. Dump all of its packets.
        for pkt in rec.packets:
            yield pkt.packet
