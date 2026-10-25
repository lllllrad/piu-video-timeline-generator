"""Check apparent cap connections throughout their independently tracked approach."""
from collections import Counter

import numpy as np

from piu_timeline.play.holds.features import ui_regions


class CapContinuity:
    """Read original color evidence even when no body candidate was detected."""

    def __init__(self, data, frames, geometry):
        self.data, self.geometry = data, geometry
        self.frames = {round(f['playback_seconds'], 6): f for f in frames if 'color_connections' in f}
        self.positions = [{round(t, 6): y*geometry.note_scale for t,y in n.get('points', [])}
                          for n in data['notes']]
        self.cache = {}

    def check(self, track):
        if not track[0].get('white_cap_bridge') or not self.frames:
            return None
        pair = []
        for edge in ('top', 'bottom'):
            extended = [p for p in track if p['long'] and edge+'_cap_note' in p]
            samples = extended if len(extended) >= 2 else track
            counts = Counter(p[edge+'_cap_note'] for p in samples if edge+'_cap_note' in p)
            ranked = counts.most_common()
            if not ranked or ranked[0][1] < 2 or ranked[0][1] < .8*sum(counts.values()):
                return None
            pair.append(ranked[0][0])
        head, tail = pair
        if head == tail or self.data['notes'][head]['target_seconds'] >= self.data['notes'][tail]['target_seconds']:
            return None
        key = tuple(pair)
        if key not in self.cache:
            self.cache[key] = self.measure(head, tail, track[0]['lane'])
        return self.cache[key]

    def measure(self, head, tail, lane):
        geometry = self.geometry
        upper, lower = self.positions[head], self.positions[tail]
        shared = sorted(upper.keys() & lower.keys() & self.frames.keys())
        if not shared:
            return None
        separations = [lower[t]-upper[t] for t in shared]
        distance = float(np.median(separations))
        if not .6*geometry.spacing <= distance <= 3*geometry.spacing:
            return None
        x = self.data['layout']['lanes'][lane]['x']
        connected, gaps, weak = [], [], []
        times = []
        for t in shared:
            y = round((upper[t]+lower[t])/2)
            # Exclude clipped caps, changing cap registration and HUD cuts.
            if (upper[t] <= geometry.receptor+1.2*geometry.spacing
                    or lower[t] >= self.data['layout'].get('note_y_max', .95)*geometry.height
                    or abs(lower[t]-upper[t]-distance) > 1.5
                    or any(rx <= x <= rx+rw and ry*geometry.height-2 <= y <= (ry+rh)*geometry.height+2
                           for rx,ry,rw,rh in ui_regions(self.data['layout']))):
                continue
            frame = self.frames[t]
            colors = frame['color_connections'][lane]
            present = any(lo <= y < hi for lo,hi in colors['connected'])
            absent = any(lo <= y < hi for lo,hi in colors['disconnected'])
            (connected if present else gaps if absent else weak).append(frame['source_pts_seconds'])
            times.append(t)
        if len(times) < 8 or times[-1]-times[0] < .12:
            return None
        # A persistent background separation refutes a hold. Short flashes of
        # touching colored corners must not outweigh the rest of the approach.
        decision = ('disconnected_caps' if len(gaps) >= .8*len(times) else
                    'connected_caps' if len(connected) >= .8*len(times) else 'unresolved')
        return {'decision': decision, 'head_note': head, 'tail_note': tail,
                'connected_source_pts_seconds': connected, 'gap_source_pts_seconds': gaps,
                'weak_source_pts_seconds': weak,
                'visible_start_seconds': times[0], 'visible_end_seconds': times[-1]}
