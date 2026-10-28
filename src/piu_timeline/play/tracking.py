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


class NoteTracker:
    def __init__(self, layout, width, height, skin_bank=None):
        self.layout, self.width, self.height = layout, width, height
        self.spacing = float(np.median(np.diff([lane['x'] * width for lane in layout['lanes']])))
        self.active, self.finished = [], []
        self.hold_candidate, self.unsupported_intervals = False, []
        from piu_timeline.play.motion import ScrollMotion
        self.motion = ScrollMotion(height, self.spacing)
        self.skin_detector = None
        self.skin_observations = []
        if skin_bank is not None:
            from piu_timeline.play.skins.detector import SkinDetector
            self.skin_detector = SkinDetector(skin_bank, layout, width, height)
            from piu_timeline.play.skins.held import BodyAtReceptor
            self.body_at_receptor = BodyAtReceptor(self.skin_detector)

    def detect(self, rgb):
        if self.skin_detector is not None:
            self.skin_observations = self.skin_detector.detect(rgb)
            self.hold_candidate = self.body_at_receptor(self.skin_observations)
            return [o for o in self.skin_observations if o['role'] != 'hold_body']
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        h, s, v = cv2.split(hsv)
        colors = {'blue': (h >= 85) & (h <= 130),
                  'red': (h <= 15) | (h >= 150),
                  'yellow': (h >= 15) & (h <= 45)}
        white = ((rgb.min(axis=2) > 175) & (rgb.max(axis=2) - rgb.min(axis=2) < 80)).astype('uint8')
        contours, _ = cv2.findContours(white, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        detections = []
        receptor = self.layout['receptor_y'] * self.height
        for contour in contours:
            x, y, w, height = cv2.boundingRect(contour)
            if not (.65*self.spacing < w < 1.25*self.spacing and .65*self.spacing < height < 1.25*self.spacing):
                continue
            cy, cx = y + height/2, x + w/2
            if not receptor + .55*self.spacing < cy < self.layout.get('note_y_max', .95)*self.height:
                continue
            index = min(range(len(self.layout['lanes'])),
                        key=lambda i: abs(self.layout['lanes'][i]['x']*self.width-cx))
            lane = self.layout['lanes'][index]
            if abs(lane['x']*self.width-cx) > .2*self.spacing:
                continue
            quality = float((colors[lane['color']] & (s > 90) & (v > 140))[y:y+height,x:x+w].mean())
            if quality < .12:
                continue
            if any(n['lane'] == index and abs(n['y']*self.height-cy) < .4*self.spacing for n in detections):
                continue
            detections.append({'lane': index, 'x': lane['x'], 'y': cy/self.height, 'quality': quality,
                               'method': 'colored_head_outline'})
        # Keep hold evidence separate from the head centers. Colored rings are
        # disconnected, but a continuous long colored body indicates a tail.
        self.hold_candidate = False
        top = int(receptor + .45*self.spacing)
        bottom = int(self.layout.get('note_y_max', .95)*self.height)
        for lane in self.layout['lanes']:
            cx = lane['x']*self.width
            left, right = max(0,int(cx-.43*self.spacing)), min(self.width,int(cx+.43*self.spacing))
            mask = (colors[lane['color']] & (s > 105) & (v > 170))[top:bottom,left:right].astype('uint8')
            _, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
            if any(height > 1.25*self.spacing and w > .2*self.spacing and y < .25*self.spacing
                   and area > self.spacing**2*.10 for x,y,w,height,area in stats[1:]):
                self.hold_candidate = True
        return detections

    def update(self, seconds, detections, source_pts=None):
        self.motion.update(seconds, detections, source_pts)
        if self.hold_candidate:
            if self.unsupported_intervals and seconds - self.unsupported_intervals[-1]['end_seconds'] < .1:
                self.unsupported_intervals[-1]['end_seconds'] = seconds
            else:
                self.unsupported_intervals.append({'start_seconds': seconds, 'end_seconds': seconds,
                                                   'reason': 'possible_hold_or_dense_stack'})
        pairs = []
        for i, track in enumerate(self.active):
            last_t, last_y = track.points[-1]
            dt = seconds - last_t
            recent = track.points[-6:]
            if len(recent) >= 2:
                ts = [t-last_t for t, _ in recent]
                ys = [y for _, y in recent]
                n = len(recent)
                velocity = (n*sum(t*y for t,y in zip(ts,ys))-sum(ts)*sum(ys)) / (n*sum(t*t for t in ts)-sum(ts)**2)
            else:
                velocity = -self.spacing*8
            prediction = last_y + velocity * dt
            displacement = self.motion.distance(last_t, seconds)
            if displacement is not None:
                prediction = last_y-displacement
            for j, note in enumerate(detections):
                y = note['y'] * self.height
                if note['lane'] == track.lane and -.25 * self.spacing <= last_y - y <= self.spacing * 30 * dt:
                    distance = abs(y - prediction)
                    if distance <= self.spacing * .8:
                        pairs.append((distance, i, j))
        used_tracks, used_notes = set(), set()
        for _, i, j in sorted(pairs):
            if i in used_tracks or j in used_notes:
                continue
            self.active[i].points.append((seconds, detections[j]['y'] * self.height))
            self.active[i].missed = 0
            used_tracks.add(i); used_notes.add(j)
        for i, track in enumerate(self.active):
            if i not in used_tracks:
                track.missed += 1
        # Judgment/combo graphics can briefly cover a moving head. Retain its
        # prediction for a bounded source-time gap instead of just two frames.
        def gap_limit(track):
            region = self.layout.get('combo_roi')
            if region is not None and len(track.points) >= 4:
                x,y,w,h = region
                px = self.layout['lanes'][track.lane]['x']
                py = track.points[-1][1]/self.height
                if x-.10 <= px <= x+w+.10 and y-.18 <= py <= y+h+.10:
                    return .35
            return .12
        expired = [track for track in self.active if seconds - track.points[-1][0] > gap_limit(track)]
        self.finished += expired
        self.active = [track for track in self.active if seconds - track.points[-1][0] <= gap_limit(track)]
        for j, note in enumerate(detections):
            if j not in used_notes:
                self.active.append(Track(note['lane'], [(seconds, note['y'] * self.height)]))

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
            if len(fragments) > 1:
                note['tracking_method'] = 'corroborated_fragments'
                if note.get('fit_method') not in ('shared_scroll_clock', 'shared_scroll_interpolation'):
                    note['fit_method'] = 'corroborated_fragments'
                note['source_track_fragments'] = fragments
            notes.append(note)
            tracks.append(track)
        from piu_timeline.play.shared_timing import restore
        self.motion,self.timing_reconstruction = restore(notes,tracks,self.motion.samples,self.layout,self.width,self.height)
        # One arrow can yield multiple disconnected colored components. Keep the
        # best trajectory when same-lane crossings coincide within two frames.
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
