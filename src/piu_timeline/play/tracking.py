"""Visual note trajectories and frame-bracketed combo events, without per-frame OCR."""
from dataclasses import dataclass, field
import math

import cv2
import numpy as np

from piu_timeline.play.frames import TIME_EPSILON


@dataclass
class Track:
    lane: int
    points: list = field(default_factory=list)
    missed: int = 0
    tracking_observations: list = field(default_factory=list)
    tracking_warnings: list = field(default_factory=list)


class NoteTracker:
    def __init__(self, layout, width, height, skin_bank=None):
        self.layout, self.width, self.height = layout, width, height
        self.spacing = float(np.median(np.diff([lane['x'] * width for lane in layout['lanes']])))
        self.active, self.finished = [], []
        self.hold_candidate, self.unsupported_intervals = False, []
        from piu_timeline.play.motion import ScrollMotion
        self.motion = ScrollMotion(height, self.spacing)
        self.skin_detector = None
        self.frame_centers = None
        self.frame_steps = []
        self.skin_observations = []
        if skin_bank is not None:
            from piu_timeline.play.skins.detector import SkinDetector
            self.skin_detector = SkinDetector(skin_bank, layout, width, height)
            from piu_timeline.play.skins.frame_centers import FrameCenters
            self.frame_centers = FrameCenters(self.skin_detector)
            from piu_timeline.play.skins.held import BodyAtReceptor
            self.body_at_receptor = BodyAtReceptor(self.skin_detector)

    def detect(self, rgb):
        if self.skin_detector is not None:
            self.skin_observations = self.skin_detector.detect(rgb)
            self.hold_candidate = self.body_at_receptor(self.skin_observations)
            return [o for o in self.skin_observations if o['role'] != 'hold_body']
        raise ValueError('Image note-skin bank required for note detection')

    def gap_limit(self,track):
        region=self.layout.get('combo_roi')
        if region is not None and len(track.points)>=4:
            x,y,w,h=region;px=self.layout['lanes'][track.lane]['x'];py=track.points[-1][1]/self.height
            if x-.10<=px<=x+w+.10 and y-.18<=py<=y+h+.10:return .35
        return .12

    def observations(self,seconds,detections):
        result=[]
        for image in detections:
            if self.frame_centers is not None:position=self.frame_centers.position(image)
            else:
                # Direct non-image callers provide normalized cap-center coordinates.
                center={'yPixels':image['y']*self.height,'uncertaintyPixels':.5,'basis':{'kind':'native_cap_center'}}
                position={'anchor':center,'center':center}
            result.append({'time':seconds,**position})
        return result

    def update(self, seconds, detections, source_pts=None):
        from piu_timeline.derived import call,CONTRACTS
        observations=self.observations(seconds,detections)
        centers=[{**image,'y':point['center']['yPixels']/self.height}for image,point in zip(detections,observations,strict=True)if point['center']]
        self.motion.update(seconds,centers,source_pts)
        if self.hold_candidate:
            if self.unsupported_intervals and seconds - self.unsupported_intervals[-1]['end_seconds'] < .1:
                self.unsupported_intervals[-1]['end_seconds'] = seconds
            else:
                self.unsupported_intervals.append({'start_seconds': seconds, 'end_seconds': seconds,
                                                   'reason': 'possible_hold_or_dense_stack'})
        assignment=call('frameTracking.assign',
            [{'lane':t.lane,'observations':t.tracking_observations,'maximumGapSeconds':self.gap_limit(t)}for t in self.active],
            [{'lane':n['lane'],'observation':o}for n,o in zip(detections,observations,strict=True)],seconds,self.spacing,[],self.frame_steps)
        self.frame_steps=[s for s in self.frame_steps if seconds-s['toSeconds']<=.35]
        if assignment['step']:self.frame_steps.append(assignment['step'])
        used_tracks, used_notes = set(), set()
        for i,j in assignment['matches']:
            self.active[i].points.append((seconds, detections[j]['y'] * self.height))
            self.active[i].tracking_observations.append(observations[j])
            self.active[i].tracking_observations=self.active[i].tracking_observations[-CONTRACTS['frame_tracking']['history_frames']:]
            self.active[i].missed = 0
            used_tracks.add(i); used_notes.add(j)
        for i, track in enumerate(self.active):
            if i not in used_tracks:
                track.missed += 1
        uncertain=set(assignment['ambiguousTracks'])
        warning={'reason':'ambiguous_note_tracking','check':'note_visibility',
                 'visible_start_seconds':seconds,'visible_end_seconds':seconds,'source_pts_seconds':[source_pts],
                 'observed_points':len(assignment['ambiguities']),
                 'candidate_edges':[{'previous_lane':self.active[i].lane,'previous_seconds':self.active[i].points[-1][0],
                    'previous_image_y_pixels':self.active[i].points[-1][1],
                    'observed_lane':detections[j]['lane'],'observed_image_y_pixels':detections[j]['y']*self.height,
                    'current_observation_index':j}for i,j in assignment['ambiguities']]}
        for i in uncertain:self.active[i].tracking_warnings.append(warning)
        expired = [track for i,track in enumerate(self.active)if i in uncertain or seconds-track.points[-1][0]>self.gap_limit(track)]
        self.finished += expired
        self.active = [track for i,track in enumerate(self.active)if i not in uncertain and seconds-track.points[-1][0]<=self.gap_limit(track)]
        for j, note in enumerate(detections):
            if j not in used_notes:
                self.active.append(Track(note['lane'],[(seconds,note['y']*self.height)],
                    tracking_observations=[observations[j]],
                    tracking_warnings=[warning]if j in assignment['ambiguousDetections']else[]))

    def finish(self):
        from piu_timeline.play.fragments import stitch_tracks, same_native_head
        notes = []
        tracks = []
        from piu_timeline.play.shared_timing import registered_motion
        source_tracks=self.finished+self.active
        registered=registered_motion(source_tracks,self.motion.samples,self.height,self.spacing,
                                     self.layout['receptor_y']*self.height,self.layout.get('note_y_max',.95)*self.height)
        for track, fragments in stitch_tracks(source_tracks, self.layout['receptor_y'] * self.height, self.spacing,
                                              motion=registered, layout=self.layout):
            note = fit_track(track, self.layout['receptor_y'] * self.height, self.spacing, motion=self.motion, layout=self.layout)
            warnings=[w for i in fragments for w in source_tracks[i].tracking_warnings]
            if warnings:note['tracking_warnings']=warnings
            if len(fragments) > 1:
                note['tracking_method'] = 'corroborated_fragments'
                if note.get('fit_method') not in ('shared_scroll_clock', 'shared_scroll_interpolation'):
                    note['fit_method'] = 'corroborated_fragments'
                note['source_track_fragments'] = fragments
                if getattr(track,'fragment_connections',None):note['fragment_connections']=track.fragment_connections
            notes.append(note)
            tracks.append(track)
        from piu_timeline.play.shared_timing import restore
        self.motion,self.timing_reconstruction = restore(notes,tracks,self.motion.samples,self.layout,self.width,self.height)
        # Multiple image comparisons can describe one cap. Merge only when
        # co-observed positions establish the same head, preserving nearby notes.
        kept = []
        for index in sorted(range(len(notes)), key=lambda i: (notes[i].get('prediction_uncertainty_seconds', math.inf),
                                                              -len(notes[i]['points']))):
            note = notes[index]
            if note['status'] != 'estimated':
                continue
            duplicate = next((j for j in kept if notes[j]['lane'] == note['lane']
                              and abs(notes[j]['target_seconds'] - note['target_seconds']) < .035
                              and same_native_head(note,notes[j])), None)
            if duplicate is not None:
                note.update(status='excluded', reason='duplicate_head_component', duplicate_of=duplicate)
            else:
                kept.append(index)
        return notes


def fit_track(track, receptor_y, spacing, motion=None, layout=None):
    from piu_timeline.derived import call
    if motion is not None:
        shared=motion.fit(track,receptor_y,layout)
        if shared is not None:
            return {'lane':track.lane,'points':[[float(t),float(y)]for t,y in track.points],**shared}
    return call('tracks.fitTrack',{'lane':track.lane,'points':track.points,
        'registration_uncertainty_pixels':getattr(track,'registration_uncertainty_pixels',0)},receptor_y,spacing)



def glyphs(rgb, threshold=175):
    """Segment white combo digits; reject noise instead of guessing a number."""
    binary = ((rgb.min(axis=2) > threshold) & (rgb.max(axis=2) - rgb.min(axis=2) < 65)).astype('uint8')
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    components = []
    for label, (x, y, w, h, area) in enumerate(stats[1:count], 1):
        if h >= rgb.shape[0] * .40 and h <= rgb.shape[0] * .98 and area >= 8 and w <= rgb.shape[1] * .4:
            components.append((int(x), (labels[y:y+h, x:x+w] == label).astype('uint8')))
    components.sort(key=lambda item: item[0])
    if not 1 <= len(components) <= 5:
        return []
    normalized = []
    for _, component in components:
        h, w = component.shape
        scale = min(18 / w, 28 / h)
        resized = cv2.resize(component, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_NEAREST)
        canvas = np.zeros((32, 22), dtype='uint8')
        top, left = (32 - resized.shape[0]) // 2, (22 - resized.shape[1]) // 2
        canvas[top:top+resized.shape[0], left:left+resized.shape[1]] = resized
        normalized.append(canvas)
    return normalized


class DigitReader:
    def __init__(self):
        self.examples = {str(i): [] for i in range(10)}
        self.sources = {str(i): set() for i in range(10)}
        self.training_call = 0
        self._comparison = None

    def train(self, rgb, value, source=None):
        self.training_call += 1
        source = str(source if source is not None else self.training_call)
        digits = glyphs(rgb)
        text = str(value)
        if len(digits) != len(text) or not text.isdigit():
            return False
        # Contradicting a strongly recognized existing glyph must not poison
        # the font bank when neural OCR misreads stylized counter text.
        if any(self._read_digits([image], None)[0] not in (None, int(digit))
               and self._read_digits([image], None)[1] >= .9 for digit,image in zip(text,digits)):
            return False
        for digit, image in zip(text, digits):
            self.examples[digit] = (self.examples[digit] + [image])[-24:]
            self.sources[digit].add(source)
        self._comparison = None
        return True

    def save(self, path):
        arrays = {}
        for digit, examples in self.examples.items():
            arrays['digit_' + digit] = np.asarray(examples, dtype='uint8').reshape(-1, 32, 22)
            arrays['sources_' + digit] = np.asarray(sorted(self.sources[digit]), dtype=str)
        np.savez_compressed(path, **arrays)

    @classmethod
    def load(cls, path):
        reader = cls()
        with np.load(path, allow_pickle=False) as bank:
            for digit in reader.examples:
                reader.examples[digit] = list(bank['digit_' + digit])
                reader.sources[digit] = set(bank['sources_' + digit].tolist())
        return reader

    def read(self, rgb, expected=None, recover=True):
        primary = self._read_digits(glyphs(rgb), expected)
        if primary[0] is not None or not recover:
            return primary
        options = []
        for threshold in (190, 205):
            result = self._read_digits(glyphs(rgb, threshold), expected)
            if result[0] is not None and result[1] >= .82:
                options.append(result)
        if options and len({value for value,_ in options}) == 1:
            self.last_mode = 'threshold_template'
            return max(options, key=lambda result: result[1])
        if not options:
            from piu_timeline.play.counter_pixels import contrast_thresholds
            contrast=[self._read_digits(glyphs(rgb,t),None)for t in contrast_thresholds(rgb)]
            if (len(contrast)==2 and all(value is not None and score>=.82 for value,score in contrast)
                    and len({value for value,_ in contrast})==1):
                self.last_mode='contrast_template'
                return min(contrast,key=lambda result:result[1])
        self.last_mode = 'unreadable'
        return None, 0.0

    def _read_digits(self, digits, expected):
        self.last_mode = 'unreadable'
        if not digits:
            return None, 0.0
        if self._comparison is None:
            examples, labels = [], []
            for digit, images in self.examples.items():
                if len(self.sources[digit]) >= 2:
                    examples.extend(images)
                    labels.extend([digit]*len(images))
            templates = np.asarray(examples, dtype='uint8').reshape(-1,32,22)
            self._comparison = templates, templates.sum(axis=(1,2)), np.asarray(labels)
        templates, sizes, labels = self._comparison
        distributions = []
        for image in digits:
            overlaps = 2*np.count_nonzero(templates & image, axis=(1,2))/np.maximum(1,sizes+image.sum())
            scores = {digit: float(overlaps[labels == digit].max()) for digit in set(labels)}
            distributions.append(scores)
        ranked = [sorted(scores.items(), key=lambda pair: pair[1], reverse=True) for scores in distributions]
        if all(scores and scores[0][1] >= .82 and (len(scores) == 1 or scores[0][1]-scores[1][1] >= .035)
               for scores in ranked):
            self.last_mode = 'independent_template'
            return int(''.join(scores[0][0] for scores in ranked)), min(scores[0][1] for scores in ranked)
        if expected is None:
            return None, 0.0
        # A nearby counter value may disambiguate a glyph, but every glyph must
        # still visually agree. Never fill an absent or unsegmented counter.
        options = []
        for value in set(range(expected, expected+11)) | set(range(10)):
            text = str(value)
            if len(text) != len(digits):
                continue
            scores = [distribution.get(digit, 0) for distribution,digit in zip(distributions,text)]
            if min(scores) >= .78:
                options.append((sum(scores)/len(scores), min(scores), value))
        options.sort(reverse=True)
        if options and (len(options) == 1 or options[0][0]-options[1][0] >= .035/len(digits)):
            self.last_mode = 'temporal_template'
            return options[0][2], options[0][1]
        return None, 0.0


class ComboTracker:
    def __init__(self):
        self.stable = None
        self.last_seen = None
        self.pending = None
        self.events = []
        self.observations = []

    def update(self, seconds, value, confidence=None, read_mode=None, source_pts=None):
        if value is None:
            return
        self.observations.append({'playback_seconds':seconds,'value':value,'confidence':confidence or 0,
                                  'read_mode':read_mode,'source_pts_seconds':source_pts})
        # Impossible positive jumps and high-valued backwards reads are usually
        # split/misclassified glyphs. They must not replace the stable baseline.
        if self.stable is not None and value != self.stable:
            elapsed = seconds - self.last_seen
            if value - self.stable > max(10, 50 * elapsed) or value < self.stable and value > 10:
                return
        if value == self.stable:
            self.last_seen = seconds
            self.pending = None
            return
        if self.pending is None or self.pending['value'] != value:
            self.pending = {'value': value, 'first': seconds, 'previous': self.last_seen}
            return
        previous = self.pending['previous']
        if self.stable is not None and previous is not None:
            delta = value - self.stable
            bounded = 1 <= delta <= 10 and self.pending['first']-previous <= .1+TIME_EPSILON
            self.events.append({'before': self.stable, 'after': value, 'delta': delta,
                                'lower_seconds': previous, 'upper_seconds': self.pending['first'],
                                'confirmation_seconds':seconds,
                                'status': 'candidate' if bounded else 'excluded',
                                'reason': None if bounded
                                else 'combo_reset' if delta <= 0 else 'combo_jump_or_observation_gap'})
        self.stable, self.last_seen, self.pending = value, seconds, None


def associate(notes,combo_events,window=.045,display_delay=0.0,event_note_constraints=None):
    from piu_timeline.derived import call
    fields=('lane','status','target_seconds')
    return call('association.associate',[{k:n[k]for k in fields if k in n}for n in notes],
                combo_events,window,display_delay,event_note_constraints,mutated=(1,))
