"""Lane-specific long-note geometry and sustained recognition, separate from taps."""
from bisect import bisect_left, bisect_right
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
ASSOCIATION_FORMAT = {'schema': 1, 'revision': 14}


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
                from .play_receptors import fractions
                scores = fractions(image, data['layout'])
                target.write(json.dumps({'source_pts_seconds': pts, 'playback_seconds': time,
                                         'bodies': bodies, 'receptor_lit': lit, 'receptor_white_fraction': scores}) + '\n')
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


def contextual_hold_support(data, frames, receptor, spacing):
    """Recover dim hold pulses using local change, body contact and a HUD update.

    These observations support an already reconstructed hold only. They never
    become tap onsets or a physical press/release measurement.
    """
    times = [frame['playback_seconds'] for frame in frames]
    events = []
    for kind in ('combo_events', 'judgment_events'):
        for index, event in enumerate(data.get(kind, [])):
            lo, hi = event['lower_seconds'], event['upper_seconds']
            positive = (event.get('delta', 0) > 0 if kind == 'combo_events' else
                        event.get('label') in ('PERFECT', 'GREAT', 'GOOD', 'BAD'))
            if positive and 0 <= hi-lo <= .12:
                events.append((hi, {'kind': kind, 'index': index, 'range': [lo, hi]}))
    events.sort(key=lambda item: item[0])
    event_times = [item[0] for item in events]
    result = {}
    for fi, frame in enumerate(frames):
        values = frame.get('receptor_white_fraction')
        if values is None or frame.get('common_receptor_flash'):
            continue
        time = frame['playback_seconds']
        nearby = [item[1] for item in events[bisect_left(event_times, time-.04):bisect_right(event_times, time+.04)]]
        if not nearby:
            continue
        previous = frames[bisect_left(times, time-.15):bisect_right(times, time-.025)]
        if len(previous) < 3 or any('receptor_white_fraction' not in item for item in previous):
            continue
        for lane, value in enumerate(values):
            if value < .4:
                continue
            baseline = float(np.quantile([item['receptor_white_fraction'][lane] for item in previous], .25))
            others = [score for li, score in enumerate(values) if li != lane]
            if value-baseline < .16 or value-float(np.median(others)) < .2:
                continue
            if not any(body['lane'] == lane and body['top'] <= receptor+.8*spacing
                       and body['bottom'] >= receptor+.6*spacing for body in frame['bodies']):
                continue
            result[(fi, lane)] = nearby
    return result


def reconstruct(data, frames):
    width = FEATURE_FORMAT['width']
    height = round(width * data['game_roi'][3] / data['game_roi'][2])
    spacing = float(np.median(np.diff([lane['x'] * width for lane in data['layout']['lanes']])))
    receptor = data['layout']['receptor_y'] * height
    holds = []
    frame_times = [frame['playback_seconds'] for frame in frames]
    contextual = contextual_hold_support(data, frames, receptor, spacing)
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
        support_start = start[1] if censored else start[0]
        # A flash can temporarily hide the body's colored pixels. Use the
        # independently recorded receptor state in neighboring native frames,
        # bounded by the reconstructed hold, not only frames with a body box.
        first_support = bisect_left(frame_times, support_start)
        support = frames[first_support:bisect_right(frame_times, last_time)]
        for fi, frame in enumerate(support, first_support):
            corroboration = contextual.get((fi, lane), [])
            if frame['receptor_lit'][lane] is not True and not corroboration:
                continue
            time, pts = frame['playback_seconds'], frame['source_pts_seconds']
            if segments and time - segments[-1]['upper_seconds'] <= .075:
                segments[-1].update(upper_seconds=time, last_source_pts_seconds=pts,
                                    frames=segments[-1]['frames']+1)
            else:
                segments.append({'lower_seconds': time, 'upper_seconds': time,
                                 'first_source_pts_seconds': pts, 'last_source_pts_seconds': pts, 'frames': 1})
            if corroboration:
                segment = segments[-1]
                segment['contextual_frames'] = segment.get('contextual_frames', 0)+1
                updates = segment.setdefault('corroborating_updates', [])
                for update in corroboration:
                    if update not in updates:
                        updates.append(update)
        segments = [segment for segment in segments if segment['frames'] >= 2 or segment.get('contextual_frames')]
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
    runs, current, known, bridge, hidden_light = [], {}, {}, {}, {}
    previous_time = None
    for frame in frames:
        time = frame['playback_seconds']
        continuous = previous_time is None or 0 < time-previous_time <= .075
        for lane, lit in enumerate(frame['receptor_lit']):
            if not continuous:
                bridge[lane] = False
                hidden_light[lane] = False
            previous = current.get(lane)
            if previous is not None and previous['lit'] == lit and continuous:
                previous.update(end_seconds=frame['playback_seconds'], last_source_pts_seconds=frame['source_pts_seconds'], frames=previous['frames']+1)
            else:
                run = {'lane': lane, 'lit': lit, 'start_seconds': frame['playback_seconds'],
                       'end_seconds': frame['playback_seconds'], 'frames': 1,
                       'first_source_pts_seconds': frame['source_pts_seconds'], 'last_source_pts_seconds': frame['source_pts_seconds'],
                       'previous_seconds': previous['end_seconds'] if previous else None,
                       'previous_lit': previous['lit'] if previous else None}
                runs.append(run); current[lane] = run
                if lit is True:
                    before = known.get(lane)
                    run['onset_range'] = None
                    if (bridge.get(lane) and before is not None and before['lit'] is False
                            and time-before['end_seconds'] <= .15):
                        run['onset_range'] = [before['end_seconds'], time]
                        run['onset_source_pts_seconds'] = [before['last_source_pts_seconds'], frame['source_pts_seconds']]
                    if (hidden_light.get(lane) and before is not None and before['lit'] is True
                            and 0 < time-before['end_seconds'] <= .15):
                        # Corroborate the earlier observed onset, without filling
                        # unknown frames or inventing a second onset after flash.
                        before['corroborating_lit_frames_after_flash'] = 1
                        before['corroborating_source_pts_seconds'] = frame['source_pts_seconds']
                        before['corroborating_playback_seconds'] = time
            if lit is None:
                bridge[lane] = bridge.get(lane, False) and frame.get('common_receptor_flash', False)
                hidden_light[lane] = (continuous and frame.get('common_receptor_flash', False)
                                      and (hidden_light.get(lane, False) or previous is not None and previous['lit'] is True))
            else:
                known[lane] = current[lane]
                bridge[lane] = lit is False
                hidden_light[lane] = False
        previous_time = time
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
    from .play_receptors import observations, reject_common_flashes
    frames = reject_common_flashes(frames, observations(data, output, frames))
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
    if not data.get('hold_analysis'):
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
    # A dense interval is a warning about hold ticks, not proof that every
    # other lane is a hold. Retain strict row alignments until lane evidence
    # can distinguish an independent tap from sustained recognition.
    input_matches = list(data['matches'])
    assigned = {match['note'] for match in input_matches}
    deferred = []
    for match in data.get('deferred_matches', []):
        index = match['note']
        if index in assigned or notes[index]['status'] != 'estimated' or notes[index].get('note_type') == 'hold':
            continue
        event = data['combo_events'][match['combo_event']]
        if event.get('delta') != 1:
            continue
        lo, hi = match['combo_lower_seconds'], match['combo_upper_seconds']
        conflict = False
        for other in input_matches:
            other_lo = other.get('observation_lower_seconds', other.get('combo_lower_seconds'))
            other_hi = other.get('observation_upper_seconds', other.get('combo_upper_seconds'))
            if (other_lo is not None and other_hi is not None and abs(other_hi-hi) <= .025
                    and other_lo <= hi and other_hi >= lo
                    and abs(other['target_seconds']-match['target_seconds']) >= .025):
                conflict = True
                break
        if not conflict:
            deferred.append({**match, 'evidence_source': 'combo+lane_onset',
                             'observation_lower_seconds': lo, 'observation_upper_seconds': hi,
                             'recovery_method': 'strict_row_alignment_with_independent_lane_onset'})
    input_matches.extend(deferred)
    from .play_receptors import onset_overlaps
    guard = 2*(data.get('median_frame_interval_seconds') or .017)
    runs = data['hold_analysis'].get('receptor_runs', [])
    owners, note_runs = {}, {}
    for match in input_matches:
        index = match['note']
        if index in suppressed:
            continue
        lo = match.get('observation_lower_seconds', match.get('combo_lower_seconds'))
        hi = match.get('observation_upper_seconds', match.get('combo_upper_seconds'))
        if lo is None or hi is None:
            continue
        for ri, run in enumerate(runs):
            if run['lane'] == notes[index]['lane'] and onset_overlaps(run, lo, hi, guard):
                owners.setdefault(ri, set()).add(index)
                note_runs.setdefault(index, []).append(ri)
    def independent_onset(note_index):
        return any(owners[ri] == {note_index} for ri in note_runs.get(note_index, []))
    matches, ambiguous = [], []
    recovered = []
    for match in input_matches:
        if match['note'] in suppressed:
            continue
        lo = match.get('observation_lower_seconds', match.get('combo_lower_seconds'))
        hi = match.get('observation_upper_seconds', match.get('combo_upper_seconds'))
        needs_onset = match.get('recovery_method') == 'strict_row_alignment_with_independent_lane_onset'
        if (needs_onset or lo is not None and hi is not None and during_hold(lo, hi)) and not independent_onset(match['note']):
            ambiguous.append(match['note'])
        else:
            matches.append(match)
            if needs_onset:
                recovered.append(match['note'])
    def events(key):
        result = []
        owned = {match.get('combo_event' if key == 'combo_events' else 'judgment_event') for match in matches}
        for event_index, event in enumerate(data.get(key, [])):
            event = dict(event)
            if key == 'combo_events' and event_index in owned and event.get('reason') == 'possible_hold_or_dense_stack':
                event.update(status='matched', reason='tap_with_independent_lane_onset_during_dense_interval')
            if event.get('label') != 'MISS' and event.get('delta', 1) > 0 and during_hold(event['lower_seconds'], event['upper_seconds']):
                if event_index in owned:
                    event.update(status='matched', reason='tap_with_independent_lane_onset_during_hold')
                else:
                    event.update(status='hold_state_or_tap', reason='ongoing_hold_tick_not_new_press')
            result.append(event)
        return result
    from .play_recovery import recover_rows
    matches, lane_recovered = recover_rows({**data, 'notes': notes, 'matches': matches,
                                          'combo_events': events('combo_events'),
                                          'judgment_events': events('judgment_events'),
                                          'hold_analysis': {**data['hold_analysis'], 'holds': projected}})
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
            'hold_tick_ambiguous_notes': [index for index in ambiguous if index not in lane_recovered],
            'recovered_dense_notes': recovered, 'recovered_lane_supported_notes': lane_recovered,
            'hold_analysis': {**data['hold_analysis'], 'holds': projected}, 'coverage': coverage}
