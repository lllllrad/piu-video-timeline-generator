"""Lane-specific long-note geometry and sustained recognition, separate from taps."""
from collections import Counter
from hashlib import sha256
from itertools import zip_longest
import json
import math
from pathlib import Path

import cv2
import numpy as np

from .play_frames import decode_frames
from .play_tracking import Track, fit_track

FEATURE_FORMAT = {'schema': 1, 'detector_revision': 4, 'width': 325}
ASSOCIATION_FORMAT = {'schema': 1, 'revision': 8}


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def feature_contract(data):
    return {'format': FEATURE_FORMAT, **{key: data[key] for key in
            ('media', 'start_seconds', 'end_seconds', 'game_roi', 'layout')}}


def detect_bodies(rgb, layout):
    """Observe colored vertical bodies and filled receptors without reading text."""
    height, width = rgb.shape[:2]
    spacing = float(np.median(np.diff([lane['x'] * width for lane in layout['lanes']])))
    receptor = layout['receptor_y'] * height
    hue, saturation, value = cv2.split(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV))
    colors = {'blue': (hue >= 85) & (hue <= 130), 'red': (hue <= 28) | (hue >= 150),
              'yellow': (hue >= 15) & (hue <= 45)}
    white = (rgb.min(axis=2) > 190) & (rgb.max(axis=2) - rgb.min(axis=2) < 65)
    bodies, lit = [], []
    top, bottom = max(0, int(receptor - .3 * spacing)), min(height, int(layout.get('note_y_max', .95) * height))
    for index, lane in enumerate(layout['lanes']):
        cx = lane['x'] * width
        left, right = max(0, int(cx - .38 * spacing)), min(width, int(cx + .38 * spacing))
        ry1, ry2 = max(0, int(receptor - .28 * spacing)), min(height, int(receptor + .28 * spacing))
        rx1, rx2 = max(0, int(cx - .28 * spacing)), min(width, int(cx + .28 * spacing))
        lit.append(float(white[ry1:ry2, rx1:rx2].mean()) > .55)
        mask = (colors[lane['color']] & (saturation > 105) & (value > 170))[top:bottom, left:right].astype('uint8')
        # Small holes from judgment text can split an otherwise continuous body.
        original_mask = mask.copy()
        kernel = np.ones((max(3, round(.6 * spacing)) | 1, 1), dtype='uint8')
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        for component, (x, y, w, h, area) in enumerate(stats[1:count], 1):
            if h < .8 * spacing or w < .16 * spacing or area < .35 * w * h:
                continue
            stripe = (labels[y:y+h, x:x+w] == component).mean(axis=0).max()
            if stripe < .72:
                continue
            bodies.append({'lane': index, 'top': float(y + top), 'bottom': float(y + top + h),
                           'long': bool(h > 1.6 * spacing),
                           'stripe_support': float(original_mask[y:y+h, x:x+w].mean(axis=0).max()), 'tail_visible': bool(y + top + h < bottom - .65 * spacing)})
    return bodies, lit


def acquire_features(data, output):
    contract = feature_contract(data)
    header, trace = output / 'hold-features.json', output / 'hold-frames.jsonl'
    if header.is_file() and trace.is_file() and json.loads(header.read_text()).get('contract') == contract:
        return
    print('  Extracting long-note bodies and receptor states; no OCR...', flush=True)
    temporary = trace.with_suffix('.build-jsonl')
    width = FEATURE_FORMAT['width']
    original = output / 'frames.jsonl'
    count = 0
    source_before = Path(data['media']['path']).stat()
    try:
        with original.open() as saved, temporary.open('w') as target:
            frames = decode_frames(data['media'], data['start_seconds'], data['end_seconds'], data['game_roi'], width)
            for raw, decoded in zip_longest(saved, frames):
                if raw is None or decoded is None:
                    raise ValueError('Hold acquisition frame count differs from saved native frames')
                previous = json.loads(raw)
                pts, time, image = decoded
                if abs(pts - previous['source_pts_seconds']) > 1e-6 or abs(time - previous['playback_seconds']) > 1e-6:
                    raise ValueError('Hold acquisition PTS differs from saved native frames')
                bodies, lit = detect_bodies(image, data['layout'])
                target.write(json.dumps({'source_pts_seconds': pts, 'playback_seconds': time,
                                         'bodies': bodies, 'receptor_lit': lit}) + '\n')
                count += 1
                if count % 2400 == 0:
                    print(f'    Long notes: {time-data["start_seconds"]:.0f}/{data["end_seconds"]-data["start_seconds"]:.0f}s', flush=True)
        source_after = Path(data['media']['path']).stat()
        if (source_before.st_size, source_before.st_mtime_ns) != (source_after.st_size, source_after.st_mtime_ns):
            raise ValueError('Source changed during long-note acquisition')
        temporary.replace(trace)
        pending = header.with_suffix('.build-json')
        pending.write_text(json.dumps({'contract': contract, 'frame_count': count}) + '\n')
        pending.replace(header)
    finally:
        temporary.unlink(missing_ok=True)


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
    points = [(p['time'], p[endpoint] + (.45 if endpoint == 'top' else -.45) * spacing)
              for p in track if (endpoint != 'bottom' or p['tail_visible'])
              and (endpoint != 'top' or p['top'] > receptor + 1.2 * spacing)]
    fitted = fit_track(Track(track[0]['lane'], points), receptor, spacing)
    if fitted['status'] != 'estimated':
        return None
    uncertainty = fitted['prediction_uncertainty_seconds'] + .55 * spacing / abs(fitted['velocity_pixels_per_second'])
    return [fitted['target_seconds'] - uncertainty, fitted['target_seconds'] + uncertainty]


def tail_from_head_track(data, track, spacing, start):
    """Corroborate a tail-shaped arrow with the connected body's lower edge."""
    visible = {round(point['time'], 6): point for point in track if point['tail_visible']}
    scale = FEATURE_FORMAT['width'] / data.get('analysis_width', FEATURE_FORMAT['width'])
    options = []
    for index, note in enumerate(data['notes']):
        velocity = note.get('velocity_pixels_per_second', 0) * scale
        if (note['status'] != 'estimated' or note['lane'] != track[0]['lane'] or velocity >= 0
                or not start + .12 <= note['target_seconds'] <= track[-1]['time'] + .25):
            continue
        errors = [abs(y*scale-(visible[round(time, 6)]['bottom']-.45*spacing))
                  for time, y in note.get('points', []) if round(time, 6) in visible]
        if len(errors) < 4 or median_error(errors) > .55*spacing:
            continue
        uncertainty = note['prediction_uncertainty_seconds'] + .55*spacing/abs(velocity)
        options.append((median_error(errors), index,
                        [note['target_seconds']-uncertainty, note['target_seconds']+uncertainty]))
    selected = min(options, default=None)
    return (selected[2], selected[1]) if selected else (None, None)


def median_error(values):
    return float(np.median(values))


def reconstruct(data, frames):
    width = FEATURE_FORMAT['width']
    height = round(width * data['game_roi'][3] / data['game_roi'][2])
    spacing = float(np.median(np.diff([lane['x'] * width for lane in data['layout']['lanes']])))
    receptor = data['layout']['receptor_y'] * height
    holds = []
    for track in body_tracks(frames, spacing):
        longs = [point for point in track if point['long'] and point.get('stripe_support', 1) >= .8]
        if len(longs) < 5 or longs[-1]['time'] - longs[0]['time'] < .08:
            continue
        lane = track[0]['lane']
        start = fit_endpoint(track, receptor, spacing, 'top')
        end = fit_endpoint(track, receptor, spacing, 'bottom')
        contact = [point for point in track if point['top'] <= receptor + .8 * spacing]
        if not start and not contact:
            continue
        censored = start is None
        if start is None:
            start = [data['start_seconds'], contact[0]['time']]
        if end and end[1] - (start[1] if censored else start[0]) < .12:
            continue
        if not end and censored and (not contact or contact[-1]['time']-contact[0]['time'] < .12):
            continue
        middle = contact[0]['time'] if censored else sum(start) / 2
        # Prefer a fitted arrow head corroborated by the approaching body.
        heads = [(i, note) for i, note in enumerate(data['notes']) if note['status'] == 'estimated'
                 and note['lane'] == lane and abs(note['target_seconds'] - middle) <= .15]
        head = min(heads, key=lambda item: abs(item[1]['target_seconds']-middle), default=None)
        if head and (not censored or track[0]['time'] < head[1]['target_seconds'] - .065):
            censored = False
            start = [head[1]['target_seconds']-head[1]['prediction_uncertainty_seconds'],
                     head[1]['target_seconds']+head[1]['prediction_uncertainty_seconds']]
        last_time = end[1] if end else track[-1]['time']
        tail_note = None
        if end is None:
            end, tail_note = tail_from_head_track(data, track, spacing, start[1] if censored else sum(start)/2)
            last_time = end[1] if end else track[-1]['time']
        if censored and end is None and head is None:
            continue
        if last_time <= (start[1] if censored else start[0]):
            continue
        # A held state is lane-local visual support. Repeated accepted ticks do
        # not create separate presses, and disappearance does not measure release.
        segments = []
        for point in contact:
            if not point['lit'] or point['time'] < start[0] or point['time'] > last_time:
                continue
            if segments and point['time'] - segments[-1]['upper_seconds'] <= .075:
                segments[-1].update(upper_seconds=point['time'], last_source_pts_seconds=point['pts'],
                                    frames=segments[-1]['frames']+1)
            else:
                segments.append({'lower_seconds': point['time'], 'upper_seconds': point['time'],
                                 'first_source_pts_seconds': point['pts'], 'last_source_pts_seconds': point['pts'], 'frames': 1})
        segments = [segment for segment in segments if segment['frames'] >= 2]
        covered = [i for i, note in enumerate(data['notes']) if note['status'] == 'estimated'
                   and note['lane'] == lane and (start[1] if censored else start[0])-.025 <= note['target_seconds'] <= last_time+.025]
        hold = {'id': len(holds), 'lane': lane, 'start_range': start, 'end_range': end,
                'start_censored': censored, 'end_censored': end is None,
                'last_body_seconds': track[-1]['time'], 'head_note': head[0] if head else None, 'tail_note': tail_note,
                'covered_notes': covered, 'body_frames': len(track), 'long_body_frames': len(longs),
                'source_pts_range': [track[0]['pts'], track[-1]['pts']],
                'input': {'kind': 'sustained_recognition', 'segments': segments,
                          'press_range': None, 'release_range': None,
                          'recognition_envelope': [segments[0]['lower_seconds'], segments[-1]['upper_seconds']] if segments else None,
                          'note': 'Filled receptor with a long body is hold-state evidence, not repeated presses or a measured switch release.'}}
        duplicate = next((previous for previous in holds if previous['lane'] == lane
                          and ((head is not None and previous['head_note'] == head[0])
                               or abs((previous['start_range'][1] if previous['start_censored'] else sum(previous['start_range'])/2) - (start[1] if censored else sum(start)/2)) < .08
                               or previous['end_range'] is not None and end is not None and abs(sum(previous['end_range'])/2-sum(end)/2) < .08)), None)
        if duplicate:
            if (not hold['start_censored'], hold['end_range'] is not None, hold['body_frames']) > (not duplicate['start_censored'], duplicate['end_range'] is not None, duplicate['body_frames']):
                hold['id'] = duplicate['id']; holds[duplicate['id']] = hold
        else:
            holds.append(hold)
    return holds


def receptor_runs(frames):
    runs, current = [], {}
    for frame in frames:
        for lane, lit in enumerate(frame['receptor_lit']):
            previous = current.get(lane)
            if previous is not None and previous['lit'] == lit:
                previous.update(end_seconds=frame['playback_seconds'], last_source_pts_seconds=frame['source_pts_seconds'], frames=previous['frames']+1)
            else:
                run = {'lane': lane, 'lit': lit, 'start_seconds': frame['playback_seconds'],
                       'end_seconds': frame['playback_seconds'], 'frames': 1,
                       'first_source_pts_seconds': frame['source_pts_seconds'], 'last_source_pts_seconds': frame['source_pts_seconds'],
                       'previous_seconds': previous['end_seconds'] if previous else None}
                runs.append(run); current[lane] = run
    return runs


def augment_holds(data, output):
    # Synthetic/legacy metadata without source stream geometry cannot reacquire
    # pixels; keep it explicit rather than invoking a decoder with invented data.
    if not data.get('media', {}).get('video_streams') or any('color' not in lane for lane in data.get('layout', {}).get('lanes', [])):
        return data
    contract = feature_contract(data)
    association = {'format': ASSOCIATION_FORMAT, 'notes': fingerprint(data['notes'])}
    path = output / 'holds.json'
    if path.is_file():
        saved = json.loads(path.read_text())
        if saved.get('feature_contract') == contract and saved.get('association_contract') == association:
            return {**data, 'hold_analysis': saved}
    acquire_features(data, output)
    with (output / 'hold-frames.jsonl').open() as stream:
        frames = [json.loads(line) for line in stream]
    holds = reconstruct(data, frames)
    result = {'feature_contract': contract, 'association_contract': association, 'holds': holds, 'receptor_runs': receptor_runs(frames),
              'semantics': 'Long notes are sustained states. Hold ticks are not independent presses; release is not measured.'}
    pending = path.with_suffix('.build-json')
    pending.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    pending.replace(path)
    return {**data, 'hold_analysis': result}


def presentation(data):
    """Project hold-aware chart/recognition without rewriting native tap evidence."""
    holds = data.get('hold_analysis', {}).get('holds', [])
    if not holds:
        return data
    notes = [dict(note) for note in data['notes']]
    suppressed = {index for hold in holds for index in hold['covered_notes']}
    for index in suppressed:
        notes[index].update(status='excluded', reason='long_note_body_or_tail', note_type='hold_component')
    projected = []
    for original in holds:
        hold = dict(original)
        start = hold['start_range']
        target = start[1] if hold['start_censored'] else sum(start)/2
        head = hold['head_note']
        if head is None or head not in suppressed:
            head = len(notes)
            notes.append({'lane': hold['lane'], 'points': [], 'target_seconds': target})
        notes[head].update(status='estimated', reason=None, note_type='hold', hold_id=hold['id'],
                           target_seconds=target,
                           prediction_uncertainty_seconds=0 if hold['start_censored'] else (start[1]-start[0])/2)
        hold['display_note'] = head
        projected.append(hold)
    def during_hold(lo, hi):
        return any(hi >= (hold['start_range'][1] if hold['start_censored'] else sum(hold['start_range'])/2) + .04
                   and lo <= (sum(hold['end_range'])/2 if hold['end_range'] else hold['last_body_seconds'])
                   for hold in holds)
    matches, ambiguous = [], []
    for match in data['matches']:
        if match['note'] in suppressed:
            continue
        lo = match.get('observation_lower_seconds', match.get('combo_lower_seconds'))
        hi = match.get('observation_upper_seconds', match.get('combo_upper_seconds'))
        if lo is not None and hi is not None and during_hold(lo, hi):
            ambiguous.append(match['note'])
        else:
            matches.append(match)
    def events(key):
        result = []
        for event in data.get(key, []):
            event = dict(event)
            if event.get('label') != 'MISS' and event.get('delta', 1) > 0 and during_hold(event['lower_seconds'], event['upper_seconds']):
                event.update(status='hold_state_or_tap', reason='ongoing_hold_tick_not_new_press')
            result.append(event)
        return result
    coverage = dict(data.get('coverage', {}))
    coverage.update(visible_note_heads=sum(note['status']=='estimated' for note in notes),
                    timed_note_heads=len(matches),
                    matched_combo_updates=len({match['combo_event'] for match in matches if match.get('combo_event') is not None}),
                    judgment_only_note_heads=sum(match.get('evidence_source') == 'judgment' for match in matches),
                    judgment_labeled_note_heads=sum(bool(match.get('judgment_label')) for match in matches),
                    unlabeled_timed_note_heads=sum(not match.get('judgment_label') for match in matches),
                    combo_frame_labeled_note_heads=sum(match.get('judgment_label_source') == 'post_combo_frames' for match in matches),
                    long_notes=len(holds),
                    sustained_recognition_spans=sum(len(hold['input']['segments']) for hold in holds))
    limitations = [item.replace('Holds, rolls', 'Rolls') for item in data.get('limitations', [])]
    limitations.append('Long-note recognition is a sustained visual state; neither a separate press per tick nor physical release is measured.')
    return {**data, 'notes': notes, 'matches': matches, 'limitations': limitations,
            'excluded_notes': dict(Counter(note.get('reason') for note in notes if note['status'] == 'excluded')),
            'miss_candidates': [candidate for candidate in data.get('miss_candidates', []) if candidate['note'] not in suppressed],
            'combo_events': events('combo_events'), 'judgment_events': events('judgment_events'),
            'hold_tick_ambiguous_notes': ambiguous,
            'hold_analysis': {**data['hold_analysis'], 'holds': projected}, 'coverage': coverage}
