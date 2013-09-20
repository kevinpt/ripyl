#!/usr/bin/python
# -*- coding: utf-8 -*-

'''Annotated protocol plotting
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

import numpy as np

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import string

import ripyl.streaming as stream



class AnnotationStyle(object):
    '''Set styling for plot annotation boxes'''
    def __init__(self, color, alpha, text_color='black', angle=0.0):
        self.color = color
        self.alpha = alpha
        self.text_color = text_color
        self.angle = angle

annotation_styles = {
    'frame': AnnotationStyle('orange', 0.2),
    'data0': AnnotationStyle('blue', 0.3),
    'data1': AnnotationStyle('#5050FF', 0.3), # lighter blue
    'addr': AnnotationStyle('green', 0.3),
    'ctrl': AnnotationStyle('orange', 0.3),
    'check_good': AnnotationStyle('yellow', 0.3),
    'check_bad': AnnotationStyle('red', 0.3),
    'ack_good': AnnotationStyle('#008F00', 0.3), # dark green
    'ack_bad': AnnotationStyle('red', 0.3),
    'misc': AnnotationStyle('0.4', 0.3)
}

# Color sequence for waveform traces (bottom to top)
plot_colors = ('blue', 'red', 'green')

class Plotter(object):
    '''Manage annotated waveform plotting'''
    def __init__(self):
        self.fig = None
        self.axes = None
        self.data_ix = 0

    def waveform_bounds(self, raw_samples):
        '''Retrieve the y-axis boundaries for annotation elements'''
        max_wf = max(raw_samples)
        min_wf = min(raw_samples)
        span = max_wf - min_wf
        
        # Overlay bounds
        ovl_top = max_wf + span * 0.15
        ovl_bot = min_wf - span * 0.05
        
        bounds = {
            'max': max_wf,
            'min': min_wf,
            'ovl_top': ovl_top,
            'ovl_bot': ovl_bot,
        }
        
        return bounds

    def plot(self, channels, annotations, title='', label_format=stream.AnnotationFormat.Int, show_names=False):
        '''Plot annotated waveform data

        channels (dict of string:sample stream)
            A dict of waveform sample data keyed by the string label
            used for each channel's vertical axis.

        annotations (sequence of StreamRecord)
            The annotation data produced by a protocol decoder

        title (string)
            Title for the plot

        label_format (AnnotationFormat)
            data format to apply for annotation records with a data_format attribute
            equal to AnnotationFormat.General

        show_names (bool)

        '''

        # Get raw samples and time vectors from channel streams
        vectors = {}
        for k in channels.keys():
            wf, start_time, sample_period = stream.extract_all_samples(channels[k])
            t = np.arange(start_time, start_time + len(wf) * sample_period - (sample_period / 2), sample_period)
            vectors[k] = (wf, t)

        self.fig, self.axes = plt.subplots(len(channels), 1, sharex=True, sharey=True)

        if not hasattr(self.axes, '__len__'):
            self.axes = (self.axes,)

        #print('$$$ axes:', self.axes)

        # Plot waveforms
        for i, (ax, k) in enumerate(zip(self.axes, channels.keys())):
            color_ix = (i - len(self.axes) + 1) % len(plot_colors)
            color = plot_colors[color_ix]
            #print('### plotting:', color, len(vectors[k][1]), len(vectors[k][0]))
            ax.plot(vectors[k][1], vectors[k][0], color=color)
            ax.set_ylabel(k)

        self.axes[0].set_title(title)
        self.axes[-1].set_xlabel('Time (s)')


        # Draw annotation rectangles
        ann_chan = channels.keys()[-1]
        ann_ax = self.axes[-1]

        ann_b = self.waveform_bounds(vectors[ann_chan][0])
        text_ypos = (ann_b['max'] + ann_b['ovl_top']) / 2.0 #FIX: this needs to be more adaptable

        if show_names:
            name_ypos = (text_ypos + ann_b['max']) / 2.0
        else:
            name_ypos = None

        self.axes[-1].set_ylim(ann_b['ovl_bot'] * 1.05, ann_b['ovl_top'] * 1.05)
        self.axes[-1].set_xlim(vectors[ann_chan][1][0], vectors[ann_chan][1][-1])


        for a in annotations:
            if not isinstance(a, stream.StreamSegment):
                continue

            self.data_ix = 0
            self._plot_patches(a, ann_b, ann_ax)

            # Draw annotation text
            self._draw_text(a, text_ypos, ann_ax, label_format, name_ypos)

        self.fig.tight_layout()
        self.fig.subplots_adjust(bottom=0.12)



    def show(self):
        '''Show the result of plot() in an interactive window'''
        if self.fig is not None:
            plt.show()

    def save_plot(self, fname, figsize=None):
        '''Save the result of plot() to a file

        fname (string)
            Name of the file to save a plot image to

        figsize ((number,number))
            The (x,y) dimensions of the image in inches. Matplotlib uses 100DPI.
        '''
        if self.fig is not None:
            if figsize is not None:
                self.fig.set_size_inches(figsize)
            self.fig.savefig(fname)


    def _plot_patches(self, a, ann_b, ann_ax):
        '''Recursively generate colored rectangles for annotations'''

        if a.data_format != stream.AnnotationFormat.Invisible:
            p_start = a.start_time
            p_end = a.end_time
            bot = ann_b['ovl_bot']
            width = p_end - p_start
            height = ann_b['ovl_top'] - bot

            style = a.style
            if style == 'data':
                style = 'data{}'.format(self.data_ix)
                self.data_ix = 1 - self.data_ix

            elif style == 'check':
                style = 'check_good' if a.status == stream.StreamStatus.Ok else 'check_bad'

            elif style == 'ack':
                style = 'ack_good' if a.status == stream.StreamStatus.Ok else 'ack_bad'

            if style in annotation_styles:
                color = annotation_styles[style].color
                alpha = annotation_styles[style].alpha

            else: # Default
                color = 'red'
                alpha = 0.2

            p_rect = patches.Rectangle((p_start, bot), width, height, facecolor=color, alpha=alpha)
            ann_ax.add_patch(p_rect)

        inset_b = ann_b.copy()
        span = inset_b['max'] - inset_b['min']
        inset_b['ovl_top'] = inset_b['max'] + span * 0.01
        inset_b['ovl_bot'] = inset_b['min'] - span * 0.01

        #print('$$$$ overlay:', ann_b['ovl_top'], inset_b['ovl_top'], ann_b['i_ovl_top'])

        for sr in a.subrecords:
            self._plot_patches(sr, inset_b, ann_ax)


    def _draw_text(self, a, text_ypos, ann_ax, label_format, name_ypos=None):
        '''Recursively generate text labels'''
        if 'value' in a.fields:
            label = a.fields['value']
        else:
            label = a.text(label_format)
        if len(label) > 0:
            size = 'small' if a.data_format == stream.AnnotationFormat.Enum else 'large'
            ann_ax.text((a.start_time + a.end_time) / 2.0, text_ypos, label, \
                size=size, ha='center', color='black', rotation=0.0)

            if name_ypos:
                try:
                    name = a.fields['name']
                except KeyError:
                    name = a.kind

                if len(name) > 0:
                    ann_ax.text((a.start_time + a.end_time) / 2.0, name_ypos, name, \
                        size='small', ha='center', color='0.4')
        

        for sr in a.subrecords:
            self._draw_text(sr, text_ypos, ann_ax, label_format, name_ypos)




