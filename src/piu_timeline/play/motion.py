"""Corroborated screen displacement and subframe clocks from visible peer notes."""
from piu_timeline.derived import CONTRACTS, call

import numpy as np


LOCAL_CLOCK_FORMAT = CONTRACTS['local_clock']


def crossing_windows(samples,before,after):
    yield from call('clocks.windows',samples,before,after)


class ScrollMotion:
    def __init__(self, height, spacing):
        self.height, self.spacing = height, spacing
        self.previous = None
        self.samples, self.at_time, self.chunks = [], {}, []
        self.clocks = {}

    def update(self, time, notes, source_pts=None):
        displacement, support, lanes, scatter = None, 0, 0, 0
        if self.previous is not None:
            before, old = self.previous
            dt = time-before
            if 0 < dt <= .075:
                pairs = [(self.height*(a['y']-b['y']), a['lane'], ai, bi)
                         for ai, a in enumerate(old) for bi, b in enumerate(notes)
                         if a['lane'] == b['lane'] and -.75 <= self.height*(a['y']-b['y']) <= self.spacing*30*dt]
                choices = []
                for center in sorted({round(pair[0]) for pair in pairs}):
                    group = sorted((pair for pair in pairs if abs(pair[0]-center) <= 1.25), key=lambda pair: abs(pair[0]-center))
                    left, right, selected = set(), set(), []
                    for pair in group:
                        if pair[2] not in left and pair[3] not in right:
                            selected.append(pair); left.add(pair[2]); right.add(pair[3])
                    if len(selected) >= 3 and len({pair[1] for pair in selected}) >= 2:
                        value = float(np.median([pair[0] for pair in selected]))
                        choices.append((len(selected), len({pair[1] for pair in selected}), value, selected))
                if choices:
                    best = max(choices, key=lambda choice: (choice[0], choice[1]))
                    rivals = [choice for choice in choices if abs(choice[2]-best[2]) > 2.5 and choice[0] >= best[0]]
                    if not rivals:
                        displacement, support, lanes = max(0, best[2]), best[0], best[1]
                        scatter = max(.35, float(np.std([pair[0] for pair in best[3]])))
        if displacement is None:
            self.chunks.append([])
            phase, variance = 0., 0.
        else:
            phase = self.samples[-1]['phase']+displacement
            variance = self.samples[-1]['variance']+scatter**2
        sample = {'time': time, 'source_pts': source_pts, 'phase': phase, 'variance': variance,
                  'chunk': len(self.chunks)-1, 'support': support, 'lanes': lanes}
        self.samples.append(sample); self.chunks[-1].append(sample); self.at_time[time] = sample
        self.previous = time, notes

    def distance(self, first, last):
        before, after = self.at_time.get(first), self.at_time.get(last)
        if (before is None or after is None or before['chunk'] != after['chunk']
                or before['chunk'] in getattr(self,'coordinate_failures',{})):
            return None
        return after['phase']-before['phase']

    def _state(self):
        return {'samples':self.samples,'height':self.height,'spacing':self.spacing,
                'strict_clock':getattr(self,'strict_clock',False),
                'coordinate_failures':getattr(self,'coordinate_failures',{}),
                'coordinate_registration':getattr(self,'coordinate_registration',{}),
                'registered_positions':getattr(self,'registered_positions',None)}

    def _track(self,track):
        return {'lane':track.lane,'points':track.points,
                'registration_uncertainty_pixels':getattr(track,'registration_uncertainty_pixels',0),
                'registration_offsets':{chunk:v for (identity,chunk),v in getattr(self,'coordinate_offsets',{}).items()if identity==id(track)}}

    def _clock(self,samples):return call('clocks.clock',samples,self.spacing)

    def crossing(self,sample,phase,phase_error):
        return call('clocks.crossing',self._state(),sample,phase,phase_error)

    def fit(self,track,receptor,layout=None):
        return call('clocks.fit',self._state(),self._track(track),receptor,layout)

    def fit_many(self,tracks,receptor,layout=None):
        return call('clocks.fitMany',self._state(),[self._track(t)for t in tracks],receptor,layout)

    def evidence(self):
        return {'format': getattr(self,'evidence_format',{'schema': 1, 'method': 'peer_note_displacement'}),
                'supported_steps': sum(sample['support'] > 0 for sample in self.samples),
                'total_steps': max(0, len(self.samples)-1), 'samples': self.samples,
                **({'coordinate_registration':self.coordinate_registration} if hasattr(self,'coordinate_registration') else {})}
