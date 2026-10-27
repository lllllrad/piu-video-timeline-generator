"""Reconstruct holds from start, body and end images, without lane-color masks."""
from collections import defaultdict

from piu_timeline.play.holds.geometry import HoldGeometry
from piu_timeline.play.holds.state import recognition_segments, recognition_window
from piu_timeline.play.skins.observations import observe


FORMAT = {'schema': 1, 'revision': 1, 'method': 'independent_image_hold_proof'}

def covered(lo, hi, boxes):
    cursor = lo
    for a, b in sorted(boxes):
        if a > cursor + 1:
            break
        cursor = max(cursor, b)
        if cursor >= hi:
            return True
    return False


def reconstruct_images(data, receptor_frames, native, diagnostics):
    records = observe(data, native)['notes']
    roles = {r['note']: {o['role'] for o in r['observations']} - {'unknown'} for r in records}
    by_time = {f['playback_seconds']: f for f in native}
    width = data['analysis_width']
    spacing = (data['layout']['lanes'][1]['x'] - data['layout']['lanes'][0]['x']) * width
    proposals, heads, tails = [], defaultdict(set), defaultdict(set)
    for head, first in enumerate(data['notes']):
        if roles[head] != {'hold_start'} or first['status'] != 'estimated':
            continue
        before = dict(first['points'])
        for tail, last in enumerate(data['notes']):
            if (roles[tail] != {'hold_end'} or last['lane'] != first['lane']
                    or last['status'] != 'estimated' or last['target_seconds'] <= first['target_seconds']):
                continue
            after = dict(last['points'])
            proof, missing = [], []
            for time in sorted(before.keys() & after.keys()):
                a, b = before[time], after[time]
                if b <= a:
                    continue
                frame = by_time[time]
                center = data['layout']['lanes'][first['lane']]['x'] * width
                boxes = [o['bounds_pixels'][1::2] for o in frame.get('skin_observations', [])
                         if o['lane'] == first['lane'] and o['role'] in ('hold_start', 'hold_body', 'hold_end')
                         and o['bounds_pixels'][0] <= center <= o['bounds_pixels'][2]
                         and o['bounds_pixels'][1] <= b and o['bounds_pixels'][3] >= a]
                if covered(a, b, boxes):
                    proof.append({'time': time, 'source_pts': frame['source_pts_seconds'], 'head_y': a, 'tail_y': b})
                else:
                    from piu_timeline.play.screen_regions import occluders_at_bounds
                    bounds = [center-.25*spacing, a, center+.25*spacing, b]
                    if not occluders_at_bounds(data['layout'],bounds,width,data['analysis_height']):
                        missing.append({'time': time, 'source_pts': frame['source_pts_seconds']})
            if (len(proof) < 4 or proof[-1]['time'] - proof[0]['time'] < .065
                    or proof[0]['head_y'] - proof[-1]['head_y'] < .5 * spacing):
                continue
            gaps = [p['tail_y'] - p['head_y'] for p in proof]
            if max(gaps) - min(gaps) > 2:
                continue
            proposals.append((head, tail, proof, missing)); heads[head].add(tail); tails[tail].add(head)
    holds, represented = [], set()
    for head, tail, proof, missing in proposals:
        if len(heads[head]) != 1 or len(tails[tail]) != 1:
            continue
        first, last = data['notes'][head], data['notes'][tail]
        def bounds(note):
            t, u = note['target_seconds'], note['prediction_uncertainty_seconds']
            return [t-u, t+u]
        holds.append({'id': len(holds), 'lane': first['lane'], 'head_note': head, 'tail_note': tail,
                      'head_observation_note': head, 'tail_observation_note': tail,
                      'covered_notes': [head, tail], 'start_range': bounds(first), 'end_range': bounds(last),
                      'start_censored': False, 'end_censored': False, 'last_body_seconds': proof[-1]['time'],
                      'body_frames': len(proof), 'body_evidence': 'skin_start_body_end_images',
                      'source_pts_range': [proof[0]['source_pts'], proof[-1]['source_pts']],
                      'image_connection_evidence': proof,
                      'component_evidence': {str(i): {'kind': 'registered_cap',
                          'source_pts_seconds': [p['source_pts'] for p in proof]} for i in (head, tail)}})
        represented.update((head, tail))
        if missing:
            diagnostics.append({'note': head, 'lane': first['lane'], 'reason': 'unresolved_hold_geometry',
                                'failure_detail': 'known_hold_image_connection_not_observed_in_clear_frames',
                                'hold': holds[-1]['id'], 'tail_note': tail,
                                'visible_start_seconds': missing[0]['time'],
                                'visible_end_seconds': missing[-1]['time'],
                                'observed_points': len(missing), 'image_evidence': missing})
    for record in records:
        index = record['note']
        if index in represented or not roles[index] & {'hold_start', 'hold_end'}:
            continue
        observations = record['observations']
        diagnostics.append({'note': index, 'lane': data['notes'][index]['lane'],
                            'reason': 'unresolved_hold_geometry', 'failure_detail': 'skin_endpoint_images_without_unique_complete_body',
                            'visible_start_seconds': min(o['playback_seconds'] for o in observations),
                            'visible_end_seconds': max(o['playback_seconds'] for o in observations),
                            'observed_points': len(observations), 'image_evidence': observations})
    accounted = {(h['lane'], p['time']) for h in holds for p in h['image_connection_evidence']}
    pending_bodies = defaultdict(list)
    for frame in native:
        for image in frame.get('skin_observations', []):
            if image['role'] == 'hold_body' and (image['lane'], frame['playback_seconds']) not in accounted:
                pending_bodies[image['lane']].append((frame['playback_seconds'], frame['source_pts_seconds'], image))
    for lane, observations in pending_bodies.items():
        diagnostics.append({'lane': lane, 'reason': 'unresolved_hold_geometry',
                            'failure_detail': 'skin_body_images_without_complete_endpoint_ownership',
                            'visible_start_seconds': observations[0][0], 'visible_end_seconds': observations[-1][0],
                            'observed_points': len(observations),
                            'image_evidence': [{'playback_seconds': t, 'source_pts_seconds': pts, **image}
                                               for t, pts, image in observations]})
    geometry = HoldGeometry.from_analysis(data, 325)
    times = [f['playback_seconds'] for f in receptor_frames]
    for hold in holds:
        hold['input'] = recognition_segments(receptor_frames, times, hold, {}, recognition_window(data, hold, geometry))
    return holds
