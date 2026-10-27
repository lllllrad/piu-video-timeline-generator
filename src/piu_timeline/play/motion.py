"""Corroborated screen displacement and subframe clocks from visible peer notes."""
from bisect import bisect_left
import math

import numpy as np


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

    def _clock(self, samples):
        if len(samples) < 16 or samples[-1]['time']-samples[0]['time'] < .3:
            return None
        t = np.array([sample['time']-samples[0]['time'] for sample in samples])
        phase = np.array([sample['phase'] for sample in samples])
        velocity, intercept = np.polyfit(t, phase, 1)
        residual = float(np.sqrt(np.mean((phase-velocity*t-intercept)**2)))
        cadence = float(np.median(np.diff([sample['time'] for sample in samples])))
        if velocity <= self.spacing or residual > max(.75,.5*cadence*velocity+.75):
            return None
        half = len(t)//2
        slopes = [np.polyfit(x, y, 1)[0] for x, y in ((t[:half], phase[:half]), (t[half:], phase[half:]))]
        uncertainty = 6*residual/max(velocity*(t[-1]-t[0]), 1)
        if abs(slopes[0]-slopes[1])/velocity > .08+uncertainty:
            return None
        return {'origin': samples[0]['time'], 'velocity': float(velocity), 'intercept': float(intercept),
                'residual': residual, 'window': [samples[0]['time'], samples[-1]['time']]}

    def extrapolated_crossing(self, sample, phase, phase_error):
        """A chord can leave the shared detector field before its target arrives."""
        chunk=self.chunks[sample['chunk']];last=chunk[-1]
        if not 0<phase-last['phase']<=1.1*self.spacing:return None
        clock=self._clock(chunk)
        if clock is None:return None
        time=clock['origin']+(phase-clock['intercept'])/clock['velocity']
        if not 0<time-last['time']<=.25:return None
        times=[s['time'] for s in self.samples];index=bisect_left(times,time)
        if not 0<index<len(times):return None
        tail=self.samples[bisect_left(times,last['time']):index+1]
        if any(b['time']-a['time']>.05+1e-6 for a,b in zip(tail,tail[1:])):return None
        # A new corroborated motion block is separate evidence; do not project
        # an old clock through it or bridge an absent recording frame.
        if any(s['support']>=2 and s['time']<=time for s in tail[1:]):return None
        before,after=self.samples[index-1:index+1]
        cadence=float(np.median(np.diff([s['time'] for s in chunk])))
        span=clock['window'][1]-clock['window'][0]
        speed_error=max(1.5,3*clock['residual'])/span
        uncertainty=max(cadence/2,(phase_error+clock['residual']+
                        speed_error*(time-last['time']))/clock['velocity'])
        return {'target_seconds':float(time),'prediction_uncertainty_seconds':float(uncertainty),
                'fit_method':'shared_scroll_clock_extrapolation','motion_clock':clock,
                'motion_support_end_seconds':last['time'],'extrapolation_seconds':float(time-last['time']),
                'crossing_source_pts_seconds':[before['source_pts'],after['source_pts']],
                'crossing_frame_seconds':[before['time'],after['time']],
                'crossing_capture_range':[before['time']-uncertainty,after['time']+uncertainty]}

    def crossing(self, sample, phase, phase_error):
        chunk = self.chunks[sample['chunk']]
        phases = [item['phase'] for item in chunk]
        index = bisect_left(phases, phase)
        if index>=len(chunk):
            from piu_timeline.play.motion_bridge import crossing as registered_crossing
            return registered_crossing(self,sample,phase,phase_error) or self.extrapolated_crossing(sample,phase,phase_error)
        if index<=0:return None
        before, after = chunk[index-1], chunk[index]
        if after['phase'] <= before['phase']:
            return None
        fraction = (phase-before['phase'])/(after['phase']-before['phase'])
        interpolated = before['time']+fraction*(after['time']-before['time'])
        phase_error += math.sqrt(max(0, after['variance']-sample['variance']))
        # Stable runs share one fitted clock. Nearby notes therefore share a
        # timing scale rather than each fitting noisy, duplicated render frames.
        if sample['chunk'] not in self.clocks:
            self.clocks[sample['chunk']] = self._clock(chunk)
        clock = self.clocks[sample['chunk']]
        if clock is None:
            local = [item for item in chunk if abs(item['time']-interpolated) <= .5]
            clock = self._clock(local)
        cadence = float(np.median(np.diff([item['time'] for item in chunk[max(0,index-8):index+8]])))
        capture_error=cadence/2
        if clock:
            proposed = clock['origin']+(phase-clock['intercept'])/clock['velocity']
            capture_error = cadence/2+phase_error/clock['velocity']
            if not before['time']-capture_error <= proposed <= after['time']+capture_error:
                clock = None
        if clock is None and getattr(self,'strict_clock',False):
            return None
        if clock:
            time = clock['origin']+(phase-clock['intercept'])/clock['velocity']
            uncertainty = max(cadence/2, (phase_error+clock['residual'])/clock['velocity'])
            method = 'shared_scroll_clock'
        else:
            time = interpolated
            velocity = (after['phase']-before['phase'])/(after['time']-before['time'])
            uncertainty = max(cadence/2, phase_error/max(velocity, 1))
            method = 'shared_scroll_interpolation'
        return {'target_seconds': float(time), 'prediction_uncertainty_seconds': float(uncertainty),
                'fit_method': method, 'motion_clock': clock,
                'crossing_source_pts_seconds': [before['source_pts'], after['source_pts']],
                'crossing_frame_seconds': [before['time'], after['time']],
                'crossing_capture_range':[before['time']-capture_error,after['time']+capture_error]}

    def fit(self, track, receptor, layout=None):
        bottom = (layout or {}).get('note_y_max', .95)*self.height-.55*self.spacing
        visible = [(time, y, self.at_time.get(time)) for time, y in track.points
                   if receptor+.85*self.spacing < y < bottom]
        if not visible or visible[-1][2] is None:
            return None
        chunk = visible[-1][2]['chunk']
        latest=[point for point in visible if point[2] is not None and point[2]['chunk']==chunk]
        if len(latest)>=4 and latest[-1][0]-latest[0][0]>=.065:
            return self._fit_visible(track,latest,receptor,layout)
        # A brief loss of peers must not erase an already measured approach.
        # Later native positions still have to validate that same bounded clock.
        groups={}
        for point in visible:
            if point[2] is not None:groups.setdefault(point[2]['chunk'],[]).append(point)
        for key,points in reversed(list(groups.items())):
            if key==chunk:continue
            later=[point for point in visible if point[0]>points[-1][0]]
            if any(p[2] is None or p[2]['support']>=2
                   or p[2]['chunk'] in getattr(self,'coordinate_failures',{}) for p in later):
                return None
            result=self._fit_visible(track,points,receptor,layout)
            if result is None:continue
            clock=result.get('motion_clock')
            if clock is None:return None
            native=[(t,y)for t,y in track.points if t>points[-1][0]]
            limit=.75+clock['velocity']*result['prediction_uncertainty_seconds']
            errors=[abs(y-(receptor+clock['velocity']*(result['target_seconds']-t)))for t,y in native]
            if (not errors or max(errors)>limit or any(t>result['target_seconds'] for t,y in native)):
                return None
            return {**result,'validated_later_observations':len(native),
                    'later_observation_maximum_error_pixels':max(errors),
                    'later_observation_tolerance_pixels':limit}
        return None

    def _fit_visible(self,track,visible,receptor,layout):
        chunk=visible[-1][2]['chunk']
        if chunk in getattr(self,'coordinate_failures',{}):return None
        if len(visible)<4 or visible[-1][0]-visible[0][0]<.065:return None
        phase = np.array([point[2]['phase'] for point in visible])
        y = np.array([point[1] for point in visible])
        if phase[-1]-phase[0] < .8*self.spacing:
            return None
        measured_slope, _ = np.polyfit(phase-phase[-1], y, 1)
        if not -1.12 <= measured_slope <= -.88:
            return None
        # Phase is measured in screen pixels. A corroborated head therefore
        # moves one pixel per phase pixel; independently fitting that slope for
        # every head would reintroduce unequal timings for equal screen gaps.
        slope = -1.
        offset=getattr(self,'coordinate_offsets',{}).get((id(track),chunk))
        intercept = float(offset-phase[-1] if offset is not None else np.median(y+phase-phase[-1]))
        errors = y+phase-phase[-1]-intercept
        inliers = abs(errors) <= .15*self.spacing
        if sum(inliers) < max(4, math.ceil(.85*len(visible))):
            return None
        residual = float(np.sqrt(np.mean(errors[inliers]**2)))
        hud = False
        if layout and layout.get('combo_roi'):
            x, top, width, height = layout['combo_roi']
            lane_x = layout['lanes'][track.lane]['x']
            hud = x-.12 <= lane_x <= x+width+.12 and top-.18 <= visible[-1][1]/self.height <= top+height+.1
        if intercept-receptor > (6 if hud else 2.5)*self.spacing:
            return None
        target_phase = float(phase[-1]+(receptor-intercept)/slope)
        error = max(.75, 2*residual/abs(slope),getattr(track,'registration_uncertainty_pixels',0))
        result = self.crossing(visible[-1][2], target_phase, error)
        if result is None or not 0 <= result['target_seconds']-visible[-1][0] <= (.65 if hud else .25):
            return None
        duration = visible[-1][0]-visible[0][0]
        return {**result, 'status': 'estimated', 'reason': None,
                'velocity_pixels_per_second': float(slope*(phase[-1]-phase[0])/duration),
                'residual_pixels': residual, 'motion_support_points': len(visible),
                'motion_target_phase': target_phase, 'motion_chunk': chunk,
                'observed_phase_slope': float(measured_slope)}

    def evidence(self):
        return {'format': getattr(self,'evidence_format',{'schema': 1, 'method': 'peer_note_displacement'}),
                'supported_steps': sum(sample['support'] > 0 for sample in self.samples),
                'total_steps': max(0, len(self.samples)-1), 'samples': self.samples,
                **({'coordinate_registration':self.coordinate_registration} if hasattr(self,'coordinate_registration') else {})}
