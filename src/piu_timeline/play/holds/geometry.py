"""Hold head/body/tail relationships in one analysis-pixel coordinate system.

See docs/gameplay-visual-model.md. Lane spacing is a scale proxy, not a
measurement of cap height; the edge offsets below retain that approximation.
"""
from dataclasses import dataclass
from collections import Counter, defaultdict

import numpy as np

from piu_timeline.play.tracking import Track, fit_track

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
        note_height = data.get('analysis_height', round(
            data.get('analysis_width', width)*data['game_roi'][3]/data['game_roi'][2]))
        return cls(width, height, data['layout']['receptor_y']*height, spacing,
                   height/note_height)


def hold_start(hold):
    start = hold['start_range']
    return start[1] if hold['start_censored'] else sum(start)/2


def register_caps(data, frames, geometry):
    """Corroborate color-stripe boundaries with independent native arrow tracks.

    Connected fill can start below an arrow's center, whereas an enclosing
    outline starts above it. Register actual centers rather than interchanging
    these two edge conventions. HUD cuts cannot nominate an endpoint.
    """
    from piu_timeline.play.fragments import same_native_head
    positions = defaultdict(list)
    for index, note in enumerate(data['notes']):
        duplicate=note.get('duplicate_of')
        if (note.get('reason')=='duplicate_head_component' and type(duplicate) is int
                and 0<=duplicate<len(data['notes']) and same_native_head(note,data['notes'][duplicate])):
            continue
        points=note.get('points',[])
        supported=(note['status']=='estimated' or len(points)>=4 and points[-1][0]-points[0][0]>=.065
                   and (points[0][1]-points[-1][1])*geometry.note_scale>.8*geometry.spacing)
        for time, y in points:
            positions[(round(time, 6), note['lane'])].append((y*geometry.note_scale,index,supported))
    result = []
    for frame in frames:
        bodies = []
        for original in frame['bodies']:
            body = dict(original)
            if body.get('edge_convention') == 'connected_color':
                nearby = positions[(round(frame['playback_seconds'], 6), body['lane'])]
                for edge, visible in (('top', body['top_visible']), ('bottom', body['tail_visible'])):
                    for suffix in ('_cap_note','_cap_y','_observed_cap_note','_observed_cap_y','_unresolved_cap_note','_unresolved_cap_y'):
                        body.pop(edge+suffix,None)
                    if not visible:
                        continue
                    options = sorted((abs(y-body[edge]), index, y,supported) for y, index,supported in nearby
                                     if abs(y-body[edge]) <= .8*geometry.spacing)
                    if options and (len(options) == 1 or options[1][0]-options[0][0] >= 1):
                        _, index, y,supported = options[0]
                        role='_observed_cap_' if supported else '_unresolved_cap_'
                        body[edge+role+'note'] = index;body[edge+role+'y'] = y
                        target=data['notes'][index].get('target_seconds')
                        if data['notes'][index]['status']=='estimated' and target is not None and np.isfinite(target):
                            body[edge+'_cap_note'] = index;body[edge+'_cap_y'] = y
            bodies.append(body)
        result.append({**frame, 'bodies': bodies})
    return result


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
                # Keep the original color topology independent from the
                # short white-border channel. A small augmented cap must not
                # steal a long body's continuation at a HUD boundary.
                if body.get('white_cap_bridge', False) != last.get('white_cap_bridge', False):
                    continue
                costs = []
                if body['tail_visible'] and last['tail_visible']:
                    costs.append(abs(body['bottom']-(last['bottom']+velocity*dt)))
                if body.get('top_visible', True) and last.get('top_visible', True):
                    costs.append(abs(body['top']-(last['top']+velocity*dt)))
                # An extended body clipped at both boundaries can remain
                # stationary while held; prefer its overlapping lower stripe
                # over a shorter HUD fragment sharing the same clipped top.
                if not costs:
                    overlap = max(0, min(last['bottom'], body['bottom'])-max(last['top'], body['top']))
                    union = max(last['bottom'], body['bottom'])-min(last['top'], body['top'])
                    cost = spacing*(1-overlap/max(union, 1))*2
                else:
                    cost = min(costs)
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
    if track[0].get('edge_convention') == 'connected_color':
        # A stripe cut by the HUD, screen or receptor is not a cap. Native
        # registered cap centers supply endpoints; absent caps remain unknown.
        points = [(p['time'], p[endpoint+'_cap_y']) for p in track if endpoint+'_cap_y' in p]
        fitted = fit_track(Track(track[0]['lane'], points), receptor, spacing)
        if fitted['status'] != 'estimated':
            return None
        uncertainty = fitted['prediction_uncertainty_seconds']
        return [fitted['target_seconds']-uncertainty, fitted['target_seconds']+uncertainty]
    points = [(p['time'], p[endpoint] + (CAP_HALF_HEIGHT if endpoint == 'top' else -CAP_HALF_HEIGHT) * spacing)
              for p in track if (endpoint != 'bottom' or p['tail_visible'])
              and (endpoint != 'top' or p['top'] > receptor + 1.2 * spacing)]
    fitted = fit_track(Track(track[0]['lane'], points), receptor, spacing)
    if fitted['status'] != 'estimated':
        return None
    uncertainty = fitted['prediction_uncertainty_seconds'] + EDGE_POSITION_TOLERANCE * spacing / abs(fitted['velocity_pixels_per_second'])
    return [fitted['target_seconds'] - uncertainty, fitted['target_seconds'] + uncertainty]


def edge_errors(note, track, spacing, scale, endpoint, receptor=None):
    """Compare registered centers at the same original source-frame times."""
    # Compare while the body is extended: a shrinking body near the receptor
    # can put its head and tail within the same positional tolerance.
    if track[0].get('edge_convention') == 'connected_color':
        visible = {round(p['time'], 6): p[endpoint+'_cap_y'] for p in track
                   if p['long'] and endpoint+'_cap_y' in p}
        return [abs(y*scale-visible[round(time, 6)]) for time, y in note.get('points', [])
                if round(time, 6) in visible]
    visible = {round(point['time'], 6): point for point in track
               if point['long'] and (point['tail_visible'] if endpoint == 'bottom'
                                    else point['top'] > receptor + 1.2*spacing)}
    offset = -CAP_HALF_HEIGHT*spacing if endpoint == 'bottom' else CAP_HALF_HEIGHT*spacing
    return [abs(y*scale-(visible[round(time, 6)][endpoint]+offset))
            for time, y in note.get('points', []) if round(time, 6) in visible]


def edge_alignment(note, track, spacing, scale, endpoint, receptor=None):
    """Compare a native arrow trajectory with an extended body's visible edge."""
    errors = edge_errors(note, track, spacing, scale, endpoint, receptor)
    if (len(errors) < MIN_EDGE_OBSERVATIONS or median_error(errors) > EDGE_POSITION_TOLERANCE*spacing
            or sum(error <= EDGE_POSITION_TOLERANCE*spacing for error in errors) < max(MIN_EDGE_OBSERVATIONS, MIN_EDGE_AGREEMENT*len(errors))):
        return None
    return median_error(errors)


def head_from_body_track(data, track, geometry, target):
    """Prefer an observed upper cap over the nearest extrapolated timestamp.

    A clipped colored box can move its predicted start towards the tail. Native
    positions distinguish those caps even when both times fit the search window.
    """
    if track[0].get('edge_convention') == 'connected_color':
        # A lone cap can precede the connected body or remain after it shrinks.
        # Its upper edge cannot distinguish head from tail. Prefer samples
        # where both caps are spatially separated by an extended body.
        extended = [p for p in track if p['long'] and 'top_cap_note' in p]
        samples = extended if len(extended) >= MIN_EDGE_OBSERVATIONS else track
        counts = Counter(p['top_cap_note'] for p in samples if 'top_cap_note' in p)
        winners = counts.most_common()
        if winners and winners[0][1] >= MIN_EDGE_OBSERVATIONS and winners[0][1] >= .8*sum(counts.values()):
            index = winners[0][0]
            return index, data['notes'][index]
        return None
    candidates = [(index, note) for index, note in enumerate(data['notes'])
                  if note['status'] == 'estimated' and note['lane'] == track[0]['lane']
                  and abs(note['target_seconds']-target) <= .15]
    aligned = []
    observed = False
    for index, note in candidates:
        errors = edge_errors(note, track, geometry.spacing, geometry.note_scale, 'top', geometry.receptor)
        observed |= len(errors) >= MIN_EDGE_OBSERVATIONS
        error = edge_alignment(note, track, geometry.spacing, geometry.note_scale, 'top', geometry.receptor)
        if error is not None:
            aligned.append((error, index, note))
    if aligned:
        aligned.sort(key=lambda option: (option[0], option[1]))
        # Subpixel residual differences do not resolve two distinct cap owners.
        if len(aligned) > 1 and aligned[1][0]-aligned[0][0] < 1:
            return None
        return aligned[0][1:]
    if observed:
        return None
    # Legacy or obscured heads without enough overlapping position observations
    # retain the temporal fallback; observed geometric contradictions do not.
    return min(candidates, key=lambda item: abs(item[1]['target_seconds']-target), default=None)


def tail_from_head_track(data, track, geometry, start):
    """Corroborate a tail-shaped arrow with the connected body's lower edge."""
    spacing, scale = geometry.spacing, geometry.note_scale
    if track[0].get('edge_convention') == 'connected_color':
        counts = Counter(p['bottom_cap_note'] for p in track if 'bottom_cap_note' in p)
        winners = counts.most_common()
        if winners and winners[0][1] >= MIN_EDGE_OBSERVATIONS and winners[0][1] >= .8*sum(counts.values()):
            index = winners[0][0]
            note = data['notes'][index]
            if note['target_seconds'] > start:
                t, u = note['target_seconds'], note['prediction_uncertainty_seconds']
                return [t-u, t+u], index
        return None, None
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


def short_cap_pair(track, geometry):
    """Four moving, strongly connected observations need not last 80 ms."""
    samples = [p for p in track if p['long'] and p.get('stripe_support',0) >= STRONG_STRIPE_SUPPORT
               and all(key in p for key in ('top_cap_note','bottom_cap_note','top_cap_y','bottom_cap_y'))
               and p['top_cap_note'] != p['bottom_cap_note']]
    if len(samples) < MIN_EDGE_OBSERVATIONS:
        return []
    pair = (samples[0]['top_cap_note'],samples[0]['bottom_cap_note'])
    if any((p['top_cap_note'],p['bottom_cap_note']) != pair for p in samples):
        return []
    if any(not 0 < b['time']-a['time'] <= .05 for a,b in zip(samples,samples[1:])):
        return []
    positions = [p['top_cap_y'] for p in samples]
    return samples if (len({round(y,1) for y in positions}) >= MIN_EDGE_OBSERVATIONS
                       and max(positions)-min(positions) >= .5*geometry.spacing) else []



def observed_cap_owner(track,edge):
    key=edge+'_observed_cap_note'
    extended=[point for point in track if point['long'] and key in point]
    samples=extended if len(extended)>=MIN_EDGE_OBSERVATIONS else track
    counts=Counter(point[key] for point in samples if key in point)
    ranked=counts.most_common()
    if ranked and ranked[0][1]>=MIN_EDGE_OBSERVATIONS and ranked[0][1]>=.8*sum(counts.values()):
        return ranked[0][0]
    return None


def resolve_geometry(data, track, geometry):
    """Return supported chart geometry, independently of displayed input state."""
    spacing, receptor = geometry.spacing, geometry.receptor
    longs = [point for point in track if point['long'] and point.get('stripe_support', 1) >= STRONG_STRIPE_SUPPORT]
    needs_edges = len(longs) < MIN_BODY_OBSERVATIONS or longs[-1]['time'] - longs[0]['time'] < MIN_BODY_SPAN_SECONDS
    if needs_edges:
        # Compression, diagonal caps and HUD overlays can reduce the colored
        # stripe fraction. Weaker pixels require BOTH tracked endpoints;
        # time proximity or one plausible edge alone cannot create a hold.
        longs = [point for point in track if point['long'] and point.get('stripe_support', 1) >= WEAK_STRIPE_SUPPORT]
        if len(longs) < MIN_BODY_OBSERVATIONS or longs[-1]['time'] - longs[0]['time'] < MIN_BODY_SPAN_SECONDS:
            longs = short_cap_pair(track,geometry)
            if not longs:
                return None
    lane = track[0]['lane']
    start = fit_endpoint(track, receptor, spacing, 'top')
    end = fit_endpoint(track, receptor, spacing, 'bottom')
    contact = [point for point in track if point['top'] <= receptor + .8 * spacing]
    head = head_from_body_track(data, track, geometry, sum(start)/2 if start else contact[0]['time'] if contact else None) if track[0].get('edge_convention') == 'connected_color' else None
    if head:
        t, u = head[1]['target_seconds'], head[1]['prediction_uncertainty_seconds']
        start = [t-u, t+u]
    if not start and not contact:
        return None
    censored = start is None
    if start is None:
        start = [data['start_seconds'], contact[0]['time']]
    short_body_fit = end is not None and end[1] - (start[1] if censored else start[0]) < .12
    middle = contact[0]['time'] if censored else sum(start) / 2
    head = head or head_from_body_track(data, track, geometry, middle)
    if head and (not censored or track[0]['time'] < head[1]['target_seconds'] - .065):
        censored = False
        start = [head[1]['target_seconds']-head[1]['prediction_uncertainty_seconds'],
                 head[1]['target_seconds']+head[1]['prediction_uncertainty_seconds']]
    if needs_edges and (censored or head is None or edge_alignment(
            head[1], track, spacing, geometry.note_scale, 'top', receptor) is None):
        return None
    # A directly tracked tail shares the native heads' motion clock. Prefer
    # it even when the noisier body-box endpoint could be extrapolated.
    tail_end, tail_note = tail_from_head_track(data, track, geometry, start[1] if censored else sum(start)/2)
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
    ownership, uncertain = {}, []
    if track[0].get('edge_convention') == 'connected_color':
        for index in covered:
            if index in (head[0] if head else None, tail_note):
                edge = 'top' if head and index == head[0] else 'bottom'
                support = [p['pts'] for p in track if p.get(edge+'_cap_note') == index]
                ownership[str(index)] = {'kind': 'registered_cap', 'source_pts_seconds': support}
                continue
            observed = {round(p['time'], 6): p for p in track if p['long']}
            overlaps = [(y*geometry.note_scale, observed[round(t, 6)])
                        for t, y in data['notes'][index].get('points', []) if round(t, 6) in observed]
            inside = [p['pts'] for y, p in overlaps if p['top'] <= y <= p['bottom']]
            if len(inside) >= MIN_EDGE_OBSERVATIONS and len(inside) >= .8*len(overlaps):
                ownership[str(index)] = {'kind': 'inside_connected_body', 'source_pts_seconds': inside}
            else:
                uncertain.append(index)
        covered = [index for index in covered if str(index) in ownership]
    return {'lane': lane, 'start_range': start, 'end_range': end,
            'start_censored': censored, 'end_censored': end is None,
            'last_body_seconds': track[-1]['time'], 'head_note': head[0] if head else None, 'tail_note': tail_note,
            'head_observation_note':observed_cap_owner(track,'top'),'tail_observation_note':observed_cap_owner(track,'bottom'),
            'covered_notes': covered, 'body_frames': len(track), 'long_body_frames': len(longs),
            'body_evidence': 'stripe_and_tracked_edges' if needs_edges else 'strong_stripe',
            'source_pts_range': [track[0]['pts'], track[-1]['pts']],
            'component_evidence': ownership, 'uncertain_components': uncertain}


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
