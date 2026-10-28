"""Reconstruct holds from start, body and end images, without lane-color masks."""
from collections import defaultdict

from piu_timeline.play.holds.geometry import HoldGeometry
from piu_timeline.play.holds.state import contextual_hold_support, recognition_segments, recognition_window
from piu_timeline.play.skins.observations import observe


FORMAT = {'schema': 1, 'revision': 11, 'method': 'independent_image_hold_proof'}

def covered(lo, hi, boxes):
    cursor = lo
    for a, b in sorted(boxes):
        if a > cursor + 1:
            break
        cursor = max(cursor, b)
        if cursor >= hi:
            return True
    return False


def reconstruct_images(data, receptor_frames, native, diagnostics, *, references=None, cap_references=None, include_state=True):
    from piu_timeline.derived import call
    data = {**data, 'notes': call('holdGeometry.inputNotes', data['notes'])}
    from piu_timeline.play.skins.coverage import reference_rows, image_spans
    references=reference_rows(data)if references is None else references
    cap_references=reference_rows(data,cap_only=True)if cap_references is None else cap_references
    from piu_timeline.play.skins.extents import LengthChecks
    lengths = LengthChecks(data)
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
                boxes = [span for o in frame.get('skin_observations', [])
                         if o['lane'] == first['lane'] and o['role'] in ('hold_start', 'hold_body', 'hold_end')
                         and o['bounds_pixels'][0] <= center <= o['bounds_pixels'][2]
                         and o['bounds_pixels'][1] <= b and o['bounds_pixels'][3] >= a
                         for span in image_spans(o,references)]
                # Use only positively compared cap pixels of known endpoints.
                # Failed connection regions supply no coverage.
                boxes.extend(span for o in frame.get('skin_observations', [])
                             if o['lane']==first['lane'] and o['role']=='unknown'
                             and o.get('classification_status')=='cap_only'
                             and min(abs(o['y']*data['analysis_height']-a),abs(o['y']*data['analysis_height']-b))<1e-5
                             for span in image_spans(o,cap_references))
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
            if max(gaps) - min(gaps) > 2 and lengths.check(head, tail)['status'] != 'consistent':
                continue
            proposals.append((head, tail, proof, missing)); heads[head].add(tail); tails[tail].add(head)
    from piu_timeline.play.skins.temporal import temporal_pairs
    existing={(head,tail):(proof,missing)for head,tail,proof,missing in proposals}
    temporal=temporal_pairs(data,native,roles,references,cap_references,length_checks=lengths)
    for pair in temporal['pairs']:
        head,tail=pair['head'],pair['tail']
        if (head,tail)in existing:
            proof,missing=existing[head,tail];times={p['time']for p in pair['proof']}
            proof[:]=sorted([*[p for p in proof if p['time']not in times],*pair['proof']],key=lambda p:p['time'])
            missing.extend(pair['missing'])
        else:proposals.append((head,tail,pair['proof'],pair['missing']))
        heads[head].add(tail);tails[tail].add(head)
    refuted={(p['head'],p['tail'])for p in temporal['refuted']}
    proposals=[p for p in proposals if p[:2]not in refuted]
    heads,tails=defaultdict(set),defaultdict(set)
    for head,tail,_,_ in proposals:heads[head].add(tail);tails[tail].add(head)
    for pair in temporal['refuted']:
        evidence=pair['evidence'];head=pair['head']
        diagnostics.append({'note':head,'lane':data['notes'][head]['lane'],'reason':'unresolved_hold_geometry',
                            'failure_detail':'skin_hold_interior_note_conflict','tail_note':pair['tail'],
                            'visible_start_seconds':min(p['time']for p in evidence),
                            'visible_end_seconds':max(p['time']for p in evidence),
                            'observed_points':len({p['time']for p in evidence}),'image_evidence':evidence})
    holds, represented = [], set()
    for head, tail, proof, missing in proposals:
        if len(heads[head]) != 1 or len(tails[tail]) != 1:
            continue
        first, last = data['notes'][head], data['notes'][tail]
        def bounds(note):
            if 'geometry_native_range' in note:
                return list(note['geometry_native_range'])
            t, u = note['target_seconds'], note['prediction_uncertainty_seconds']
            return [t-u, t+u]
        holds.append({'id': len(holds), 'lane': first['lane'], 'head_note': head, 'tail_note': tail,
                      'head_observation_note': head, 'tail_observation_note': tail,
                      'covered_notes': [head, tail], 'start_range': bounds(first), 'end_range': bounds(last),
                      'start_censored': False, 'end_censored': False, 'last_body_seconds': proof[-1]['time'],
                      'body_frames': len({p['time']for p in proof}),
                      'body_evidence': 'skin_temporal_image_regions'if any('covered_bounds_pixels'in p for p in proof)else'skin_start_body_end_images',
                      'source_pts_range': [proof[0]['source_pts'], proof[-1]['source_pts']],
                      'image_connection_evidence': proof,
                      'component_evidence': {str(i): {'kind': 'registered_cap',
                          'source_pts_seconds': sorted({p['source_pts'] for p in proof
                              if ('head_y'if i==head else'tail_y')in p})} for i in (head, tail)}})
        native_endpoints = [i for i in (head, tail) if 'geometry_native_range' in data['notes'][i]]
        if native_endpoints:
            holds[-1].update(geometry_native_endpoint_notes=native_endpoints, chart_timing_status='unresolved',
                             geometry_source_failures=[{'note': i, **data['notes'][i]['geometry_source_failure']}
                                                       for i in native_endpoints])
        extent = lengths.cache.get((head, tail))
        if extent and extent['status'] == 'consistent':
            holds[-1]['endpoint_extent_evidence'] = extent
            unverified = extent['unverified_source_pts_seconds']
            unbound = extent['unregistered_playback_seconds']
            if unverified or unbound:
                diagnostics.append({'note': head, 'lane': first['lane'], 'hold': holds[-1]['id'], 'tail_note': tail,
                                    'reason': 'unresolved_hold_geometry',
                                    'failure_detail': 'known_hold_endpoint_extent_unregistered_frames',
                                    'visible_start_seconds': min(t for t, _ in first['points']),
                                    'visible_end_seconds': max(t for t, _ in last['points']),
                                    'observed_points': len(unverified)+len(unbound),
                                    'unregistered_source_pts_seconds': unverified,
                                    'unregistered_playback_seconds': unbound})
        represented.update((head, tail))
        if missing:
            diagnostics.append({'note': head, 'lane': first['lane'], 'reason': 'unresolved_hold_geometry',
                                'failure_detail': 'known_hold_image_connection_not_observed_in_clear_frames',
                                'hold': holds[-1]['id'], 'tail_note': tail,
                                'visible_start_seconds': missing[0]['time'],
                                'visible_end_seconds': missing[-1]['time'],
                                'observed_points': len({p['time']for p in missing}), 'image_evidence': missing})
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
    accounted = defaultdict(list)
    for hold in holds:
        for point in hold['image_connection_evidence']:
            accounted[hold['lane'], point['time']].append(
                point['covered_bounds_pixels']if 'covered_bounds_pixels'in point else(point['head_y'],point['tail_y']))
    pending_bodies = defaultdict(list)
    for frame in native:
        for image in frame.get('skin_observations', []):
            owned=any(a <= image['y']*data['analysis_height'] <= b
                      for a,b in accounted[image['lane'],frame['playback_seconds']])
            if image['role'] == 'hold_body' and not owned:
                pending_bodies[image['lane']].append((frame['playback_seconds'], frame['source_pts_seconds'], image))
    for lane, observations in pending_bodies.items():
        diagnostics.append({'lane': lane, 'reason': 'unresolved_hold_geometry',
                            'failure_detail': 'skin_body_images_without_complete_endpoint_ownership',
                            'visible_start_seconds': observations[0][0], 'visible_end_seconds': observations[-1][0],
                            'observed_points': len(observations),
                            'image_evidence': [{'playback_seconds': t, 'source_pts_seconds': pts, 'trace':'frames.jsonl',
                                                **{k:image[k]for k in ('lane','x','y','role','template','bounds_pixels','region_errors')}}
                                               for t, pts, image in observations]})
    if include_state:
        from piu_timeline.play.holds.state import attach_state
        holds = attach_state(data, receptor_frames, holds, require_hold_geometry=True)
    return holds
