"""Display all observed timing alternatives without promoting them to matches."""
from collections import Counter
import math
import json

from .play_candidates import EARLY_SECONDS, LATE_SECONDS, association_window, intersect_window


def counter_frame_ranges(path):
    """Keep positive raw-reader changes as alternatives, never confirmed events."""
    previous = None
    events = []
    with path.open() as stream:
        for line in stream:
            frame = json.loads(line)
            value = frame.get('combo')
            if value is None or frame.get('combo_confidence', 0) < .8:
                continue
            current = (frame['playback_seconds'], value, frame['source_pts_seconds'])
            if previous is not None:
                delta = value - previous[1]
                if 0 < delta <= 10 and 0 < current[0] - previous[0] <= 1:
                    events.append({'delta': delta, 'lower_seconds': previous[0], 'upper_seconds': current[0],
                                   'source_pts_seconds': [previous[2], current[2]],
                                   'before': previous[1], 'after': value,
                                   'reason': 'unconfirmed_positive_counter_frame_change'})
            previous = current
    return events


def timing_ranges(data):
    matches = {match['note']: match for match in data.get('matches', [])}
    misses = {candidate['note'] for candidate in data.get('miss_candidates', [])}
    events = []
    for source, key in (('combo', 'combo_events'), ('judgment', 'judgment_events'), ('counter_frames', 'counter_frame_events')):
        for index, event in enumerate(data.get(key, [])):
            if source in ('combo', 'counter_frames') and event.get('delta', 0) <= 0:
                continue
            if source == 'judgment' and event.get('label') == 'MISS':
                continue
            lo, hi = event['lower_seconds'], event['upper_seconds']
            if math.isfinite(lo) and math.isfinite(hi) and lo <= hi:
                events.append({'source': source, 'event': index, 'delta': event.get('delta', 1), 'lower_seconds': lo,
                               'upper_seconds': hi, 'reason': event.get('reason'),
                               **({key: event[key] for key in ('before', 'after')} if 'before' in event and 'after' in event else {}),
                               **({'source_pts_seconds': event['source_pts_seconds']} if 'source_pts_seconds' in event else {})})
    holds = {hold['id']: hold for hold in data.get('hold_analysis', {}).get('holds', [])}
    from .play_candidates import candidates
    constrained, rejected = candidates(data, events)
    ordered = sorted(matches.values(), key=lambda match: match['target_seconds'])
    def bracket(match):
        return (match.get('observation_lower_seconds', match.get('combo_lower_seconds')),
                match.get('observation_upper_seconds', match.get('combo_upper_seconds')))
    result = {}
    for index, note in enumerate(data.get('notes', [])):
        if note['status'] != 'estimated':
            continue
        target, uncertainty = note['target_seconds'], note['prediction_uncertainty_seconds']
        window = association_window(note, data.get('display_delay_correction_ms', 0) / 1000)
        record = {'association_window': window, 'target_range': [target - uncertainty, target + uncertainty], 'input_ranges': [],
                  'rejected_candidates': rejected.get(index, [])}
        if note.get('note_type') == 'hold':
            hold = holds[note['hold_id']]
            ranges = [[segment['lower_seconds'], segment['upper_seconds']] for segment in hold['input']['segments']]
            result[index] = {**record, 'status': 'hold_state' if ranges else 'hold_unresolved',
                             'input_ranges': ranges, 'target_range': hold['start_range'],
                             'end_range': hold['end_range'], 'reason': 'sustained_state_not_repeated_presses',
                             'input_kind': 'sustained_recognition', 'press_range': None, 'release_range': None}
            continue
        match = matches.get(index)
        if match and match.get('judgment_label') != 'MISS':
            lo = match.get('observation_lower_seconds', match.get('combo_lower_seconds'))
            hi = match.get('observation_upper_seconds', match.get('combo_upper_seconds'))
            if lo is not None and hi is not None:
                clipped = intersect_window([lo, hi], window)
                record.update(status='matched' if clipped else 'unknown', input_ranges=[clipped] if clipped else [],
                              observed_input_range=[lo, hi],
                              reason='matched_display_refresh' if clipped else 'outside_association_window')
        if 'status' not in record:
            if index in misses or match and match.get('judgment_label') == 'MISS':
                record.update(status='possible_miss', reason='possible_miss_has_no_press_timestamp')
            else:
                # Review a wider neighborhood than strict association, including
                # delayed processing in nearby frames. Keep all alternatives and their provenance; this
                # does not assert that any event belongs to this note.
                alternatives = constrained.get(index, [])
                intervals = []
                for lo, hi in sorted(event['candidate_range'] for event in alternatives):
                    if intervals and lo <= intervals[-1][1]:
                        intervals[-1][1] = max(intervals[-1][1], hi)
                    else:
                        intervals.append([lo, hi])
                record.update(status='possible' if alternatives else 'unknown', input_ranges=intervals,
                              reason='ambiguous_display_association' if alternatives else 'nearby_refresh_rejected_by_constraints' if record['rejected_candidates'] else 'no_nearby_positive_refresh',
                              alternatives=alternatives)
                if not intervals and not record['rejected_candidates']:
                    before = next((match for match in reversed(ordered) if match['target_seconds'] < target - .025), None)
                    after = next((match for match in ordered if match['target_seconds'] > target + .025), None)
                    if before and after and after['target_seconds'] - before['target_seconds'] <= 3:
                        lo, _ = bracket(before)
                        _, hi = bracket(after)
                        clipped = intersect_window([lo, hi], window) if lo is not None and hi is not None else None
                        if clipped:
                            record.update(status='bounded', reason='between_neighboring_processed_rows',
                                          input_ranges=[clipped], neighbor_observation_range=[lo, hi], anchors=[before['note'], after['note']],
                                          condition='Bounds assume this note was pressed in chart-row order; they do not establish a press.')
        if record['status'] == 'unknown' and record['reason'] != 'outside_association_window':
            if any(event.get('delta', 0) <= 0 and event['lower_seconds'] <= target <= event['upper_seconds']
                   for event in data.get('combo_events', [])):
                record['reason'] = 'counter_reset_without_resolved_press'
            elif any(interval['start_seconds'] - .1 <= target <= interval['end_seconds'] + .1
                     for interval in data.get('unsupported_intervals', [])):
                record['reason'] = 'hold_or_dense_stack_without_resolved_refresh'
            elif events and target < min(event['lower_seconds'] for event in events):
                record['reason'] = 'before_first_detected_positive_refresh'
            elif events and target > max(event['upper_seconds'] for event in events):
                record['reason'] = 'after_last_detected_positive_refresh'
        result[index] = record
    return {'notes': result, 'counts': dict(Counter(record['status'] for record in result.values())),
            'association_limits_seconds': {'early': EARLY_SECONDS, 'late': LATE_SECONDS},
            'note': 'Connected ranges intersect original observations with hard timing limits. Possible ranges remain unconfirmed; original observations and source PTS are preserved.'}
