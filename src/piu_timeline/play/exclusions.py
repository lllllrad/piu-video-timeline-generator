"""Account for visible tracks that failed chart reconstruction; never hide gaps."""
from collections import Counter


def exclusion_diagnostics(native, projected):
    warnings, exceptions, accounted = [], [], []
    regions = projected.get('chart_policy', {}).get('regions', [])
    def represented_by_hold(index):
        for hold in projected.get('hold_analysis', {}).get('holds', []):
            proof = hold.get('component_evidence', {}).get(str(index), {})
            if (index in hold.get('covered_notes', [])
                    and proof.get('kind') in ('registered_cap', 'inside_connected_body')
                    and len(set(proof.get('source_pts_seconds', []))) >= 4):
                return True
        return False
    def corroborated_duplicate(note, owner):
        if note['lane'] != owner['lane']:
            return False
        positions = {round(t, 6): y for t, y in owner.get('points', [])}
        errors = [abs(y-positions[round(t, 6)]) for t, y in note.get('points', []) if round(t, 6) in positions]
        return len(errors) >= 4 and sum(error <= 2 for error in errors) >= .8*len(errors)
    for index, note in enumerate(native.get('notes', [])):
        points = note.get('points', [])
        if not points:
            continue
        view = projected['notes'][index]
        if view.get('reason') == 'long_note_body_or_tail' and represented_by_hold(index):
            accounted.append({'note': index, 'reason': 'represented_by_reconstructed_hold'})
            continue
        if note['status'] != 'excluded' and view.get('reason') != 'long_note_body_or_tail':
            continue
        duplicate = note.get('duplicate_of')
        if (note.get('reason') == 'duplicate_head_component' and type(duplicate) is int
                and 0 <= duplicate < len(projected['notes'])
                and corroborated_duplicate(note, projected['notes'][duplicate])
                and (projected['notes'][duplicate]['status'] == 'estimated'
                     or (projected['notes'][duplicate].get('reason') == 'long_note_body_or_tail'
                         and represented_by_hold(duplicate)))):
            accounted.append({'note': index, 'reason': 'represented_by_duplicate_owner', 'represented_by': duplicate})
            continue
        first, last = min(point[0] for point in points), max(point[0] for point in points)
        reason = 'unverified_hold_component' if view.get('reason') == 'long_note_body_or_tail' else note.get('reason') or 'unspecified_exclusion'
        record = {'note': index, 'lane': note['lane'], 'reason': reason,
                  'visible_start_seconds': first, 'visible_end_seconds': last, 'observed_points': len(points),
                  'target_seconds': note.get('target_seconds')}
        # With no trustworthy target, only an explicit exception containing the
        # entire observed trajectory may suppress a warning. Partial overlap
        # and a general annotation never excuse a missing note.
        allowed = [region['id'] for region in regions
                   if (region['processing'] in ('exclude_timing', 'hold_state_only')
                       or 'timing_evidence' in region['check_exceptions'])
                   and region['playback_start_seconds'] <= first
                   and last < region['playback_end_seconds']]
        if allowed:
            exceptions.append({**record, 'exception_regions': allowed})
        else:
            warnings.append(record)
    warnings.sort(key=lambda item: (item['visible_start_seconds'], item['lane']))
    return {'warnings': warnings, 'chart_exceptions': exceptions, 'accounted_observations': accounted,
            'counts': {'unaccounted_excluded_tracks': len(warnings), 'explicit_chart_exceptions': len(exceptions),
                       'already_represented_observations': len(accounted)},
            'reasons': dict(Counter(record['reason'] for record in warnings)),
            'note': 'Warnings are excluded visible detections, not a verified count of missing chart notes. Noise candidates remain visible for review.'}


def recognition_diagnostics(data, ranges):
    """Expose uncertain geometry, ownership and input evidence as review items."""
    warnings, exceptions, accounted = [], [], []
    regions = data.get('chart_policy', {}).get('regions', [])
    def add(record):
        record = {'observed_points': 0, **record}
        allowed = [r['id'] for r in regions
                   if (r['processing'] in ('exclude_timing', 'hold_state_only') or 'timing_evidence' in r['check_exceptions'])
                   and r['playback_start_seconds'] <= record['visible_start_seconds']
                   and record['visible_end_seconds'] < r['playback_end_seconds']]
        (exceptions if allowed else warnings).append({**record, **({'exception_regions': allowed} if allowed else {})})
    holds = data.get('hold_analysis', {}).get('holds', [])
    for hold in holds:
        lo = hold['start_range'][1] if hold['start_censored'] else hold['start_range'][0]
        hi = hold['end_range'][1] if hold['end_range'] else hold['last_body_seconds']
        base = {'hold': hold['id'], 'lane': hold['lane'], 'visible_start_seconds': lo,
                'visible_end_seconds': max(lo, hi), 'observed_points': hold.get('body_frames', 0)}
        if hold['start_censored']:
            add({**base, 'reason': 'hold_start_unresolved'})
        if hold['end_censored'] or not hold['end_range']:
            add({**base, 'reason': 'hold_end_unresolved'})
        for index in hold.get('uncertain_components', []):
            add({**base, 'note': index, 'reason': 'hold_component_ownership_unresolved'})
    for record in data.get('hold_analysis', {}).get('unresolved_tracks', []):
        connection = record.get('cap_continuity') or {}
        gaps = connection.get('gap_source_pts_seconds', [])
        seen = (len(set(gaps)) + len(set(connection.get('connected_source_pts_seconds', [])))
                + len(set(connection.get('weak_source_pts_seconds', []))))
        if (connection.get('decision') == 'disconnected_caps' and len(set(gaps)) >= 8
                and len(set(gaps)) >= .8*seen
                and connection['visible_end_seconds']-connection['visible_start_seconds'] >= .12
                and all(data['notes'][connection[key]]['status'] == 'estimated'
                        and data['notes'][connection[key]].get('note_type') != 'hold'
                        for key in ('head_note', 'tail_note'))):
            accounted.append({**record, 'interpretation': 'separate_caps_with_observed_gap'})
            continue
        # Only a matching, repeatedly observed cap identity can account for a
        # partial body track. Time/lane overlap alone never suppresses it.
        owners = [h for h in holds if h['lane'] == record['lane'] and any(
            e['note'] == h['head_note' if e['edge'] == 'top' else 'tail_note']
            and len(set(e['source_pts_seconds'])) >= 4 for e in record.get('cap_evidence', []))]
        if len(owners) == 1:
            accounted.append({**record, 'represented_by_hold': owners[0]['id']})
        else:
            add(record)
    matches = {m['note']: m for m in data.get('matches', [])}
    for index, record in ranges.get('notes', {}).items():
        index = int(index)
        note = data['notes'][index]
        base = {'note': index, 'lane': note['lane'], 'visible_start_seconds': record['target_range'][0],
                'visible_end_seconds': record['target_range'][1], 'timing_status': record['status']}
        if record['status'] not in ('matched', 'hold_state', 'policy_excluded'):
            add({**base, 'reason': 'timing_evidence_unresolved'})
        elif record['status'] == 'matched' and not matches.get(index, {}).get('judgment_label'):
            add({**base, 'reason': 'judgment_label_unresolved'})
    warnings.sort(key=lambda r: (r['visible_start_seconds'], r['lane'], r['reason']))
    return {'warnings': warnings, 'chart_exceptions': exceptions, 'accounted_hold_fragments': accounted,
            'counts': dict(Counter(r['reason'] for r in warnings))}
