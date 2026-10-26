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
    def __init__(self, layout, width, height):
        self.layout, self.width, self.height = layout, width, height
        self.spacing = float(np.median(np.diff([lane['x'] * width for lane in layout['lanes']])))
        self.active, self.finished = [], []
        self.hold_candidate, self.unsupported_intervals = False, []
        from piu_timeline.play.motion import ScrollMotion
        self.motion = ScrollMotion(height, self.spacing)

    def detect(self, rgb):
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
    result = {'lane': track.lane, 'points': [[float(t), float(y)] for t, y in track.points],
              'status': 'excluded', 'reason': None, 'target_seconds': None}
    if motion is not None:
        shared = motion.fit(track, receptor_y, layout)
        if shared is not None:
            return {**result, **shared}
    # The detection crop clips a head as it approaches the receptor. Those
    # bounding-box centers flatten even during perfectly constant scrolling.
    visible = [p for p in track.points if p[1] > receptor_y + .85 * spacing]
    if len(visible) < 4 or visible[-1][0] - visible[0][0] < .065:
        return {**result, 'reason': 'insufficient_track'}
    # A local fit must itself be linear; never use an average song scroll speed.
    points = np.asarray(visible[-12:], dtype=float)
    t = points[:, 0] - points[-1, 0]
    y = points[:, 1]
    velocity, intercept = np.polyfit(t, y, 1)
    residual = float(np.sqrt(np.mean((y - (velocity * t + intercept)) ** 2)))
    result.update(velocity_pixels_per_second=float(velocity), residual_pixels=residual)
    if velocity >= -spacing:
        return {**result, 'reason': 'stopped_or_reverse_scroll'}
    half = len(points) // 2
    first_fit = np.polyfit(t[:half], y[:half], 1)
    last_fit = np.polyfit(t[half:], y[half:], 1)
    first, last = first_fit[0], last_fit[0]
    change = abs(first - last) / max(abs(velocity), 1)
    result['speed_change_fraction'] = float(change)
    # Pixel rounding is a larger slope error for slow/short trajectories.
    quantization = 2 / max(abs(velocity) * (t[-1] - t[half]), 1)
    def slope_variance(ts, ys, fit):
        errors = ys-np.polyval(fit, ts)
        return float(np.dot(errors,errors)/max(1,len(ts)-2)/max(np.sum((ts-ts.mean())**2),1e-9))
    # Encoded frames can repeat a rendered game frame. That stepwise motion
    # produces slope noise, not acceleration. Account for its measured error.
    slope_error = 3*math.sqrt(slope_variance(t[:half],y[:half],first_fit)
                             + slope_variance(t[half:],y[half:],last_fit))/abs(velocity)
    if residual > spacing * .14 or change > .18 + quantization + slope_error:
        gaps = np.flatnonzero(np.diff(points[:,0]) > .06)
        if len(gaps):
            latest = points[gaps[-1]+1:]
            if len(latest) >= 4 and latest[-1,0]-latest[0,0] >= .065:
                recovered = fit_track(Track(track.lane, latest.tolist()), receptor_y, spacing)
                if recovered['status'] == 'estimated':
                    return {**recovered, 'points': result['points'], 'fit_method': 'linear_after_occlusion'}
        return {**result, 'reason': 'variable_speed_or_tracking_error'}
    target = float(points[-1, 0] + (receptor_y - intercept) / velocity)
    extrapolation = target - points[-1, 0]
    if not 0 <= extrapolation <= .25 or intercept - receptor_y > 2.5 * spacing:
        return {**result, 'reason': 'receptor_not_observed_closely'}
    step = float(np.median(np.diff(points[:,0])))
    held_since, hold_span = points[0,0], 0.0
    for i in range(1,len(points)):
        if abs(points[i,1]-points[i-1,1]) > .75:
            held_since = points[i,0]
        hold_span = max(hold_span, points[i,0]-held_since)
    return {**result, 'status': 'estimated', 'target_seconds': target,
            'prediction_uncertainty_seconds': max(residual / abs(velocity), (step+hold_span)/2)}


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


def associate(notes, combo_events, window=.045, display_delay=0.0, event_note_constraints=None):
    """Align judged rows, not individual heads, to observed counter increments.

    A chord is one row. A skipped counter value can cover consecutive rows,
    but each receives the original aggregate observation bracket.
    """
    rows = []
    for index, note in sorted(enumerate(notes), key=lambda item: item[1].get('target_seconds') or math.inf):
        if note['status'] != 'estimated':
            continue
        if rows and abs(note['target_seconds'] - rows[-1]['seconds']) < .025:
            rows[-1]['notes'].append(index)
        else:
            rows.append({'seconds': note['target_seconds'], 'notes': [index]})
    events = [(i, event) for i,event in enumerate(combo_events) if event['status'] == 'candidate']
    lengths = [event.get('delta',1) for _,event in events]
    weights = np.zeros((len(events),len(rows)))
    links = []
    for i,(event_index,event) in enumerate(events):
        count = lengths[i]
        center = (event['lower_seconds']+event['upper_seconds'])/2
        span = event['upper_seconds']-event['lower_seconds']
        radius = span/2+window
        if not 1 <= count <= 10:
            continue
        for j in range(len(rows)-count+1):
            group = rows[j:j+count]
            allowed = (event_note_constraints or {}).get(event_index)
            if allowed is not None and any(k not in allowed for row in group for k in row['notes']):
                continue
            if any(len({notes[k]['lane'] for k in row['notes']}) != len(row['notes']) for row in group):
                continue
            distances = [abs(row['seconds']+display_delay-center) for row in group]
            if max(distances)>radius or group[-1]['seconds']-group[0]['seconds']>span+.02:
                continue
            weights[i,j] = count*(1-.5*(sum(distances)/count/radius)**2)
            links.append((i,j,count))
    forward = np.zeros((len(events)+1,len(rows)+1))
    backward = np.zeros_like(forward)
    for i,count in enumerate(lengths):
        for end in range(1,len(rows)+1):
            paired = forward[i,end-count]+weights[i,end-count] if 0<count<=end and weights[i,end-count] else 0
            forward[i+1,end] = max(forward[i,end],forward[i+1,end-1],paired)
    for i in reversed(range(len(events))):
        count = lengths[i]
        for j in reversed(range(len(rows))):
            paired = weights[i,j]+backward[i+1,j+count] if weights[i,j] else 0
            backward[i,j] = max(backward[i+1,j],backward[i,j+1],paired)
    path,i,j = [],len(events),len(rows)
    while i and j:
        count = lengths[i-1]
        if 0<count<=j and weights[i-1,j-count] and abs(forward[i,j]-forward[i-1,j-count]-weights[i-1,j-count])<1e-9:
            path.append((i-1,j-count));i-=1;j-=count
        elif forward[i-1,j]>=forward[i,j-1]:
            i-=1
        else:
            j-=1
    accepted = {}
    optimum = forward[-1,-1]
    for i,j in path:
        count = lengths[i]
        alternatives = [forward[k,l]+weights[k,l]+backward[k+1,l+n]
                        for k,l,n in links if (k,l)!=(i,j)
                        and (k==i or l<j+count and l+n>j)]
        if not alternatives or optimum-max(alternatives)>.08:
            accepted[i]=j
    matches=[]
    for i,(event_index,event) in enumerate(events):
        if i not in accepted:
            event.update(status='excluded',reason='ambiguous_note_or_combo_association')
            continue
        event.update(status='matched',reason=None)
        for row in rows[accepted[i]:accepted[i]+lengths[i]]:
            for index in row['notes']:
                target=notes[index]['target_seconds']
                matches.append({'note':index,'combo_event':event_index,'target_seconds':target,
                                'row_note_count':len(row['notes']),'aggregate_row_count':lengths[i],
                                'combo_lower_seconds':event['lower_seconds'],'combo_upper_seconds':event['upper_seconds'],
                                'raw_offset_lower_ms':1000*(event['lower_seconds']-target),
                                'raw_offset_upper_ms':1000*(event['upper_seconds']-target)})
    return sorted(matches,key=lambda match:match['target_seconds'])
