"""Hold analysis orchestration and projection; pixels, geometry and state are separate."""
from collections import Counter
from hashlib import sha256
import json

from piu_timeline.play.holds.features import FEATURE_FORMAT, acquire_features, feature_contract
from piu_timeline.play.holds.geometry import HoldGeometry, body_tracks, hold_start, register_caps, resolve_geometry, retain_hold
from piu_timeline.play.holds.state import contextual_hold_support, recognition_segments, recognition_window, receptor_runs

ASSOCIATION_FORMAT = {'schema': 1, 'revision': 22}


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def reconstruct(data, frames, diagnostics=None):
    """Resolve chart geometry first, then attach independent recognition spans."""
    geometry = HoldGeometry.from_analysis(data, FEATURE_FORMAT['width'])
    frames = register_caps(data, frames, geometry)
    frame_times = [frame['playback_seconds'] for frame in frames]
    holds = []
    for track in body_tracks(frames, geometry.spacing):
        hold = resolve_geometry(data, track, geometry)
        if hold is None:
            extended = [p for p in track if p['long'] and p.get('stripe_support', 1) >= .72]
            if diagnostics is not None and len(extended) >= 5 and extended[-1]['time']-extended[0]['time'] >= .08:
                diagnostics.append({'lane': track[0]['lane'], 'reason': 'unresolved_hold_geometry',
                                    'visible_start_seconds': track[0]['time'], 'visible_end_seconds': track[-1]['time'],
                                    'source_pts_range': [track[0]['pts'], track[-1]['pts']], 'observed_points': len(track)})
            continue
        hold['id'] = len(holds)
        retain_hold(holds, hold)
    contextual = contextual_hold_support(data, frames, geometry.receptor, geometry.spacing, holds)
    for hold in holds:
        window = recognition_window(data, hold, geometry)
        hold['input'] = recognition_segments(frames, frame_times, hold, contextual, window)
    return holds


def augment_holds(data, output):
    # Synthetic/legacy metadata without source stream geometry cannot reacquire
    # pixels; keep it explicit rather than invoking a decoder with invented data.
    if not data.get('media', {}).get('video_streams') or any('color' not in lane for lane in data.get('layout', {}).get('lanes', [])):
        return data
    contract = feature_contract(data)
    association = {'format': ASSOCIATION_FORMAT, 'notes': fingerprint(data['notes']),
                   'hud_events': fingerprint({key: data.get(key, []) for key in ('combo_events', 'judgment_events')})}
    path = output / 'holds.json'
    if path.is_file():
        saved = json.loads(path.read_text())
        if saved.get('feature_contract') == contract and saved.get('association_contract') == association:
            return {**data, 'hold_analysis': saved}
    acquire_features(data, output)
    with (output / 'hold-frames.jsonl').open() as stream:
        frames = [json.loads(line) for line in stream]
    from piu_timeline.play.receptors import observations, reject_common_flashes
    frames = reject_common_flashes(frames, observations(data, output, frames))
    unresolved = []
    holds = reconstruct(data, frames, unresolved)
    result = {'feature_contract': contract, 'association_contract': association, 'holds': holds,
              'unresolved_tracks': unresolved, 'receptor_runs': receptor_runs(frames),
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
        target = hold_start(hold)
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
    from piu_timeline.play.receptors import onset_overlaps
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
    from piu_timeline.play.recovery import recover_rows
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
