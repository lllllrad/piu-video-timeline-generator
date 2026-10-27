"""Join independent image-role measurements to native track identities."""
from collections import Counter


def observe(data, native):
    by_time = {f['playback_seconds']: f for f in native}
    records = []
    height = data['analysis_height']
    for index, note in enumerate(data['notes']):
        observations = []
        for time, y in note.get('detected_points', note.get('points', [])):
            frame = by_time.get(time)
            if frame is None:
                raise ValueError('Image track observation has no native source frame')
            matches = [o for o in frame.get('skin_observations', []) if o['lane'] == note['lane']
                       and o['role'] != 'hold_body' and abs(o['y'] * height - y) < 1e-5]
            if len(matches) != 1:
                continue
            image = matches[0]
            role = image['role']
            observations.append({'kind': 'tap' if role == 'tap' else 'hold' if role in ('hold_start', 'hold_end') else 'unknown',
                                 'role': role, 'reason': 'skin_image_' + role, 'source_note': index,
                                 'playback_seconds': time, 'source_pts_seconds': frame['source_pts_seconds'],
                                 'trace': 'frames.jsonl', 'template': image['template'], 'skin': image['skin'],
                                 'region_errors': image['region_errors'], 'bounds_pixels': image['bounds_pixels']})
        kinds = {o['kind'] for o in observations} - {'unknown'}
        records.append({'note': index, 'status': 'conflict' if len(kinds) > 1 else next(iter(kinds)) if kinds else 'unknown',
                        'observations': observations})
    return {'format': data['skin_detector']['contract'], 'available': True, 'notes': records,
            'counts': dict(Counter(r['status'] for r in records)), 'traces': ['frames.jsonl'],
            'pixel_coordinates': {'width': data['analysis_width'], 'height': height, 'origin': 'game_crop_top_left'}}


def tail_roles(data):
    """A complete end image includes the cap and its upper body connection."""
    result = []
    for record in data.get('visual_channels', {}).get('note_types', {}).get('notes', []):
        observations = record['observations']
        if not observations or {o.get('role') for o in observations} != {'hold_end'}:
            continue
        index = record['note']
        result.append({'tail_note': index, 'head_note': None, 'lane': data['notes'][index]['lane'],
                       'status': 'observed_image_tail_timing_unresolved',
                       'visible_start_seconds': min(o['playback_seconds'] for o in observations),
                       'visible_end_seconds': max(o['playback_seconds'] for o in observations),
                       'source_pts_seconds': [o['source_pts_seconds'] for o in observations],
                       'image_evidence': observations})
    return result
