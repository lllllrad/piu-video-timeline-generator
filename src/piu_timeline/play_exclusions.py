"""Account for visible tracks that failed chart reconstruction; never hide gaps."""
from collections import Counter


def exclusion_diagnostics(native, projected):
    warnings, exceptions, accounted = [], [], []
    regions = projected.get('chart_policy', {}).get('regions', [])
    for index, note in enumerate(native.get('notes', [])):
        points = note.get('points', [])
        if not points:
            continue
        view = projected['notes'][index]
        if view.get('reason') == 'long_note_body_or_tail':
            accounted.append({'note': index, 'reason': 'represented_by_reconstructed_hold'})
            continue
        if note['status'] != 'excluded':
            continue
        duplicate = note.get('duplicate_of')
        if (note.get('reason') == 'duplicate_head_component' and type(duplicate) is int
                and 0 <= duplicate < len(projected['notes'])
                and (projected['notes'][duplicate]['status'] == 'estimated'
                     or projected['notes'][duplicate].get('reason') == 'long_note_body_or_tail')):
            accounted.append({'note': index, 'reason': 'represented_by_duplicate_owner', 'represented_by': duplicate})
            continue
        first, last = min(point[0] for point in points), max(point[0] for point in points)
        record = {'note': index, 'lane': note['lane'], 'reason': note.get('reason') or 'unspecified_exclusion',
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
