"""Join independent image-role measurements to native track identities."""
from collections import Counter


FORMAT = {'schema': 1, 'revision': 2, 'evidence': 'native_image_trace_references'}

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
            for observed_role in image.get('conflicting_roles',[role]):
                proof=next((p for p in [image,*image.get('alternatives',[])]
                            if p.get('template_role',p['role'])==observed_role
                            and p.get('classification_status','full_pattern')in('full_pattern','conflict')),image)
                observations.append({'kind': 'tap' if observed_role == 'tap' else 'hold' if observed_role in ('hold_start', 'hold_end') else 'unknown',
                                 'role': observed_role, 'reason': image.get('reason','skin_image_' + role), 'source_note': index,
                                 'playback_seconds': time, 'source_pts_seconds': frame['source_pts_seconds'],
                                 'trace': 'frames.jsonl', 'template': proof['template'], 'skin': image['skin'],
                                 'region_errors': proof['region_errors'], 'bounds_pixels': proof.get('bounds_pixels',image['bounds_pixels']),
                                 'image_anchor':[proof.get('x',image.get('x')),proof.get('y',image.get('y'))],
                                 'source_image_anchor':[image.get('x'),image.get('y')],
                                 'classification_status':proof.get('classification_status','full_pattern')})
                observations[-1].update({k:proof[k]for k in ('sampling_phase_pixels','reference_scale_y')if k in proof})
        for proof in data.get('skin_role_evidence',{}).get('notes',{}).get(str(index),[]):
            observations.append({**proof,'image_anchor':[proof['image_anchor'][0]/data['analysis_width'],
                                                        proof['image_anchor'][1]/height]})
        kinds = {o['kind'] for o in observations} - {'unknown'}
        records.append({'note': index, 'status': 'conflict' if len(kinds) > 1 else next(iter(kinds)) if kinds else 'unknown',
                        'observations': observations})
    return {'format': {'roles':FORMAT,'skin_detector':data['skin_detector']['contract'],
                      'clearance':data.get('skin_role_evidence',{}).get('contract')}, 'available': True, 'notes': records,
            'counts': dict(Counter(r['status'] for r in records)), 'traces': ['frames.jsonl'],
            'pixel_coordinates': {'width': data['analysis_width'], 'height': height, 'origin': 'game_crop_top_left'}}


def tail_roles(data):
    from piu_timeline.derived import call,projection_input
    return call('holdProjection.imageTailRoles',projection_input(data))
