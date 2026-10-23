"""Visual note trajectories and frame-bracketed combo events, without per-frame OCR."""
from dataclasses import dataclass, field
import math

import cv2
import numpy as np


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

    def detect(self, rgb):
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        h, s, v = cv2.split(hsv)
        masks = {'blue': ((h >= 85) & (h <= 130)),
                 'red': ((h <= 15) | (h >= 150)),
                 'yellow': ((h >= 15) & (h <= 45))}
        detections = []
        self.hold_candidate = False
        top = int(self.layout['receptor_y'] * self.height + .45 * self.spacing)
        bottom = int(self.layout.get('note_y_max', .95) * self.height)
        for index, lane in enumerate(self.layout['lanes']):
            cx = int(lane['x'] * self.width)
            left, right = max(0, int(cx - .43 * self.spacing)), min(self.width, int(cx + .43 * self.spacing))
            mask = (masks[lane['color']] & (s > 105) & (v > 170))[top:bottom, left:right].astype('uint8')
            count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
            for x, y, w, height, area in stats[1:count]:
                if height > 1.25 * self.spacing and w > .2 * self.spacing and y < .25 * self.spacing and area > self.spacing ** 2 * .10:
                    self.hold_candidate = True
                if not (.20 * self.spacing <= w <= self.spacing and .20 * self.spacing <= height <= 1.25 * self.spacing):
                    continue
                if area < self.spacing ** 2 * .035:
                    continue
                # Bright outlines distinguish supported note skins from BGA colors.
                y0, y1 = max(0, top + y - 3), min(self.height, top + y + height + 3)
                x0, x1 = max(0, left + x - 3), min(self.width, left + x + w + 3)
                white = (rgb[y0:y1, x0:x1].min(axis=2) > 180).mean()
                if white < .025:
                    continue
                detections.append({'lane': index, 'x': lane['x'], 'y': (top + y + height / 2) / self.height,
                                   'quality': float(min(1, area / (self.spacing ** 2 * .20)))})
        return detections

    def update(self, seconds, detections):
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
            velocity = ((last_y - track.points[-2][1]) / (last_t - track.points[-2][0])
                        if len(track.points) >= 2 else -self.spacing * 8)
            prediction = last_y + velocity * dt
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
        self.finished += [track for track in self.active if track.missed > 2]
        self.active = [track for track in self.active if track.missed <= 2]
        for j, note in enumerate(detections):
            if j not in used_notes:
                self.active.append(Track(note['lane'], [(seconds, note['y'] * self.height)]))

    def finish(self):
        return [fit_track(track, self.layout['receptor_y'] * self.height, self.spacing)
                for track in self.finished + self.active]


def fit_track(track, receptor_y, spacing):
    result = {'lane': track.lane, 'points': [[float(t), float(y)] for t, y in track.points],
              'status': 'excluded', 'reason': None, 'target_seconds': None}
    if len(track.points) < 4 or track.points[-1][0] - track.points[0][0] < .065:
        return {**result, 'reason': 'insufficient_track'}
    # A local fit must itself be linear; never use an average song scroll speed.
    points = np.asarray(track.points[-12:], dtype=float)
    t = points[:, 0] - points[-1, 0]
    y = points[:, 1]
    velocity, intercept = np.polyfit(t, y, 1)
    residual = float(np.sqrt(np.mean((y - (velocity * t + intercept)) ** 2)))
    result.update(velocity_pixels_per_second=float(velocity), residual_pixels=residual)
    if velocity >= -spacing:
        return {**result, 'reason': 'stopped_or_reverse_scroll'}
    half = len(points) // 2
    first = np.polyfit(t[:half], y[:half], 1)[0]
    last = np.polyfit(t[half:], y[half:], 1)[0]
    change = abs(first - last) / max(abs(velocity), 1)
    result['speed_change_fraction'] = float(change)
    if residual > spacing * .14 or change > .18:
        return {**result, 'reason': 'variable_speed_or_tracking_error'}
    target = float(points[-1, 0] + (receptor_y - intercept) / velocity)
    extrapolation = target - points[-1, 0]
    if not 0 <= extrapolation <= .16:
        return {**result, 'reason': 'receptor_not_observed_closely'}
    return {**result, 'status': 'estimated', 'target_seconds': target,
            'prediction_uncertainty_seconds': max(residual / abs(velocity), float(np.median(np.diff(points[:,0]))) / 2)}


def glyphs(rgb):
    """Segment white combo digits; reject noise instead of guessing a number."""
    binary = ((rgb.min(axis=2) > 175) & (rgb.max(axis=2) - rgb.min(axis=2) < 65)).astype('uint8')
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

    def train(self, rgb, value, source=None):
        self.training_call += 1
        source = source if source is not None else self.training_call
        digits = glyphs(rgb)
        text = str(value)
        if len(digits) != len(text) or not text.isdigit():
            return False
        for digit, image in zip(text, digits):
            self.examples[digit] = (self.examples[digit] + [image])[-24:]
            self.sources[digit].add(source)
        return True

    def read(self, rgb):
        digits = glyphs(rgb)
        if not digits:
            return None, 0.0
        text, confidence = '', 1.0
        for image in digits:
            scores = []
            for digit, examples in self.examples.items():
                if len(self.sources[digit]) < 2:
                    continue
                score = max(2 * np.count_nonzero(image & other) / max(1, image.sum() + other.sum())
                            for other in examples)
                scores.append((float(score), digit))
            scores.sort(reverse=True)
            if not scores or scores[0][0] < .82 or len(scores) > 1 and scores[0][0] - scores[1][0] < .035:
                return None, 0.0
            text += scores[0][1]; confidence = min(confidence, scores[0][0])
        return int(text), confidence


class ComboTracker:
    def __init__(self):
        self.stable = None
        self.last_seen = None
        self.pending = None
        self.events = []

    def update(self, seconds, value):
        if value is None:
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
            self.events.append({'before': self.stable, 'after': value, 'delta': delta,
                                'lower_seconds': previous, 'upper_seconds': self.pending['first'],
                                'status': 'candidate' if delta == 1 and self.pending['first'] - previous <= .1 else 'excluded',
                                'reason': None if delta == 1 and self.pending['first'] - previous <= .1
                                else 'combo_reset' if delta <= 0 else 'combo_jump_or_observation_gap'})
        self.stable, self.last_seen, self.pending = value, seconds, None


def associate(notes, combo_events, window=.045, display_delay=0.0):
    """Accept only unique, single-head associations; preserve ambiguous evidence."""
    rows = []
    for index, note in sorted(enumerate(notes), key=lambda item: item[1].get('target_seconds') or math.inf):
        if note['status'] != 'estimated':
            continue
        if rows and abs(note['target_seconds'] - rows[-1]['seconds']) < .025:
            rows[-1]['notes'].append(index)
        else:
            rows.append({'seconds': note['target_seconds'], 'notes': [index]})
    candidates = {}
    for i, event in enumerate(combo_events):
        if event['status'] == 'candidate':
            candidates[i] = [j for j, row in enumerate(rows)
                             if event['lower_seconds'] - window <= row['seconds'] + display_delay <= event['upper_seconds'] + window]
    use_count = {j: sum(j in options for options in candidates.values()) for j in range(len(rows))}
    matches = []
    for i, options in candidates.items():
        event = combo_events[i]
        if len(options) != 1 or use_count[options[0]] != 1:
            event.update(status='excluded', reason='ambiguous_note_or_combo_association')
            continue
        row = rows[options[0]]
        if len(row['notes']) != 1:
            event.update(status='excluded', reason='chord_or_duplicate_track')
            continue
        index = row['notes'][0]
        target = notes[index]['target_seconds']
        event['status'] = 'matched'
        matches.append({'note': index, 'combo_event': i, 'target_seconds': target,
                        'combo_lower_seconds': event['lower_seconds'], 'combo_upper_seconds': event['upper_seconds'],
                        'raw_offset_lower_ms': 1000 * (event['lower_seconds'] - target),
                        'raw_offset_upper_ms': 1000 * (event['upper_seconds'] - target)})
    return matches
