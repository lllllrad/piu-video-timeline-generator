"""Hold head/body/tail relationships in one analysis-pixel coordinate system.

See docs/gameplay-visual-model.md. Lane spacing is a scale proxy, not a
measurement of cap height; the edge offsets below retain that approximation.
"""
from dataclasses import dataclass

import numpy as np

from .play_tracking import Track, fit_track

# Measured inner cap bounds are approximately 0.9 lane spacings high in the
# reviewed skin. These are implementation tolerances, not game judgment windows.
CAP_HALF_HEIGHT = .45
EDGE_POSITION_TOLERANCE = .55
MIN_EDGE_OBSERVATIONS = 4
MIN_EDGE_AGREEMENT = .65
MIN_BODY_OBSERVATIONS = 5
MIN_BODY_SPAN_SECONDS = .08
STRONG_STRIPE_SUPPORT = .8
WEAK_STRIPE_SUPPORT = .72


@dataclass(frozen=True)
class HoldGeometry:
    width: int
    height: int
    receptor: float
    spacing: float
    note_scale: float

    @classmethod
    def from_analysis(cls, data, width):
        height = round(width * data['game_roi'][3] / data['game_roi'][2])
        spacing = float(np.median(np.diff([lane['x']*width for lane in data['layout']['lanes']])))
        return cls(width, height, data['layout']['receptor_y']*height, spacing,
                   width/data.get('analysis_width', width))


def hold_start(hold):
    start = hold['start_range']
    return start[1] if hold['start_censored'] else sum(start)/2


def body_tracks(frames, spacing):
    active, finished = [], []
    for frame in frames:
        time = frame['playback_seconds']
        expired = [track for track in active if time - track[-1]['time'] > .25]
        finished.extend(expired)
        active = [track for track in active if time - track[-1]['time'] <= .25]
        pairs = []
        for i, track in enumerate(active):
            last = track[-1]
            velocity = (last['bottom'] - track[-2]['bottom']) / (last['time'] - track[-2]['time']) if len(track) > 1 else -spacing * 8
            velocity = min(0, max(-spacing * 40, velocity))
            dt = time - last['time']
            for j, body in enumerate(frame['bodies']):
                if body['lane'] != last['lane']:
                    continue
                cost = min(abs(body['bottom'] - (last['bottom'] + velocity * dt)),
                           abs(body['top'] - (last['top'] + velocity * dt)))
                if cost < spacing * .9:
                    pairs.append((cost, i, j))
        used_tracks, used_bodies = set(), set()
        for _, i, j in sorted(pairs):
            if i in used_tracks or j in used_bodies:
                continue
            body = frame['bodies'][j]
            active[i].append({**body, 'time': time, 'pts': frame['source_pts_seconds'],
                              'lit': frame['receptor_lit'][body['lane']]})
            used_tracks.add(i); used_bodies.add(j)
        for j, body in enumerate(frame['bodies']):
            if j not in used_bodies:
                active.append([{**body, 'time': time, 'pts': frame['source_pts_seconds'],
                                'lit': frame['receptor_lit'][body['lane']]}])
    return finished + active


def fit_endpoint(track, receptor, spacing, endpoint):
    points = [(p['time'], p[endpoint] + (CAP_HALF_HEIGHT if endpoint == 'top' else -CAP_HALF_HEIGHT) * spacing)
              for p in track if (endpoint != 'bottom' or p['tail_visible'])
              and (endpoint != 'top' or p['top'] > receptor + 1.2 * spacing)]
    fitted = fit_track(Track(track[0]['lane'], points), receptor, spacing)
    if fitted['status'] != 'estimated':
        return None
    uncertainty = fitted['prediction_uncertainty_seconds'] + EDGE_POSITION_TOLERANCE * spacing / abs(fitted['velocity_pixels_per_second'])
    return [fitted['target_seconds'] - uncertainty, fitted['target_seconds'] + uncertainty]


def edge_alignment(note, track, spacing, scale, endpoint, receptor=None):
    """Compare a native arrow trajectory with an extended body's visible edge."""
    # Compare while the body is extended: a shrinking body near the receptor
    # can put its head and tail within the same positional tolerance.
    visible = {round(point['time'], 6): point for point in track
               if point['long'] and (point['tail_visible'] if endpoint == 'bottom'
                                    else point['top'] > receptor + 1.2*spacing)}
    offset = -CAP_HALF_HEIGHT*spacing if endpoint == 'bottom' else CAP_HALF_HEIGHT*spacing
    errors = [abs(y*scale-(visible[round(time, 6)][endpoint]+offset))
              for time, y in note.get('points', []) if round(time, 6) in visible]
    if (len(errors) < MIN_EDGE_OBSERVATIONS or median_error(errors) > EDGE_POSITION_TOLERANCE*spacing
            or sum(error <= EDGE_POSITION_TOLERANCE*spacing for error in errors) < max(MIN_EDGE_OBSERVATIONS, MIN_EDGE_AGREEMENT*len(errors))):
        return None
    return median_error(errors)


def tail_from_head_track(data, track, spacing, start, width):
    """Corroborate a tail-shaped arrow with the connected body's lower edge."""
    scale = width / data.get('analysis_width', width)
    options = []
    for index, note in enumerate(data['notes']):
        velocity = note.get('velocity_pixels_per_second', 0) * scale
        if (note['status'] != 'estimated' or note['lane'] != track[0]['lane'] or velocity >= 0
                or not start < note['target_seconds'] <= track[-1]['time'] + .25):
            continue
        error = edge_alignment(note, track, spacing, scale, 'bottom')
        if error is None:
            continue
        # Edge tolerance establishes identity; the native cap track already
        # supplies the crossing uncertainty. Reusing the association tolerance
        # as timing error would enlarge the hold into unrelated later taps.
        uncertainty = note['prediction_uncertainty_seconds']
        options.append((error, index,
                        [note['target_seconds']-uncertainty, note['target_seconds']+uncertainty]))
    selected = min(options, default=None)
    return (selected[2], selected[1]) if selected else (None, None)


def median_error(values):
    return float(np.median(values))


def resolve_geometry(data, track, geometry):
    """Return supported chart geometry, independently of displayed input state."""
    width, spacing, receptor = geometry.width, geometry.spacing, geometry.receptor
    longs = [point for point in track if point['long'] and point.get('stripe_support', 1) >= STRONG_STRIPE_SUPPORT]
    needs_edges = len(longs) < MIN_BODY_OBSERVATIONS or longs[-1]['time'] - longs[0]['time'] < MIN_BODY_SPAN_SECONDS
    if needs_edges:
        # Compression, diagonal caps and HUD overlays can reduce the colored
        # stripe fraction. Weaker pixels require BOTH tracked endpoints;
        # time proximity or one plausible edge alone cannot create a hold.
        longs = [point for point in track if point['long'] and point.get('stripe_support', 1) >= WEAK_STRIPE_SUPPORT]
        if len(longs) < MIN_BODY_OBSERVATIONS or longs[-1]['time'] - longs[0]['time'] < MIN_BODY_SPAN_SECONDS:
            return None
    lane = track[0]['lane']
    start = fit_endpoint(track, receptor, spacing, 'top')
    end = fit_endpoint(track, receptor, spacing, 'bottom')
    contact = [point for point in track if point['top'] <= receptor + .8 * spacing]
    if not start and not contact:
        return None
    censored = start is None
    if start is None:
        start = [data['start_seconds'], contact[0]['time']]
    short_body_fit = end is not None and end[1] - (start[1] if censored else start[0]) < .12
    middle = contact[0]['time'] if censored else sum(start) / 2
    # Prefer a fitted arrow head corroborated by the approaching body.
    heads = [(i, note) for i, note in enumerate(data['notes']) if note['status'] == 'estimated'
             and note['lane'] == lane and abs(note['target_seconds'] - middle) <= .15]
    head = min(heads, key=lambda item: abs(item[1]['target_seconds']-middle), default=None)
    if head and (not censored or track[0]['time'] < head[1]['target_seconds'] - .065):
        censored = False
        start = [head[1]['target_seconds']-head[1]['prediction_uncertainty_seconds'],
                 head[1]['target_seconds']+head[1]['prediction_uncertainty_seconds']]
    if needs_edges and (censored or head is None or edge_alignment(
            head[1], track, spacing, geometry.note_scale, 'top', receptor) is None):
        return None
    # A directly tracked tail shares the native heads' motion clock. Prefer
    # it even when the noisier body-box endpoint could be extrapolated.
    tail_end, tail_note = tail_from_head_track(data, track, spacing, start[1] if censored else sum(start)/2, width)
    if needs_edges and tail_note is None:
        return None
    if tail_end is not None:
        end = tail_end
    if short_body_fit and tail_note is None:
        return None
    last_time = end[1] if end else track[-1]['time']
    if censored and end is None and head is None:
        return None
    if last_time <= (start[1] if censored else start[0]):
        return None
    covered = [i for i, note in enumerate(data['notes']) if note['status'] == 'estimated'
               and note['lane'] == lane and (start[1] if censored else start[0])-.025 <= note['target_seconds'] <= last_time+.025]
    return {'lane': lane, 'start_range': start, 'end_range': end,
            'start_censored': censored, 'end_censored': end is None,
            'last_body_seconds': track[-1]['time'], 'head_note': head[0] if head else None, 'tail_note': tail_note,
            'covered_notes': covered, 'body_frames': len(track), 'long_body_frames': len(longs),
            'body_evidence': 'stripe_and_tracked_edges' if needs_edges else 'strong_stripe',
            'source_pts_range': [track[0]['pts'], track[-1]['pts']]}


def retain_hold(holds, hold):
    """Deduplicate fragments by supported head, start or tail identity."""
    head, end = hold['head_note'], hold['end_range']
    duplicate = next((previous for previous in holds if previous['lane'] == hold['lane']
                      and ((head is not None and previous['head_note'] == head)
                           or abs(hold_start(previous)-hold_start(hold)) < .08
                           or previous['end_range'] is not None and end is not None
                           and abs(sum(previous['end_range'])/2-sum(end)/2) < .08)), None)
    if duplicate:
        if (not hold['start_censored'], end is not None, hold['body_frames']) > (
                not duplicate['start_censored'], duplicate['end_range'] is not None, duplicate['body_frames']):
            hold['id'] = duplicate['id']
            holds[duplicate['id']] = hold
    else:
        holds.append(hold)
