"""Reconstruct holds from start, body and end images, without lane-color masks."""
from collections import defaultdict
from piu_timeline.play.observations.coordinates import detection_points

from piu_timeline.play.skins.observations import observe
from piu_timeline.play.skins.occlusion import coverage,lane_regions,supported,SUPPORT


FORMAT = {'schema': 1, 'revision': 23,'body_continuity':{'method':'consecutive_positive_body_overlap','minimum_overlap_spacing':.5,'maximum_capture_gap_seconds':.05}, 'method': 'independent_image_hold_proof',
          'interior_caps':'separate_observed_objects',
          'motion_peers':'explicit_fit_trajectory_displacement',
          'cap_coverage':'all_qualified_cap_comparisons',
          'coverage_prediction':'intersection_of_source_bound_displacements',
          'temporal_body_support':'qualified_body_or_endpoint_connection_regions',
          'direct_support':SUPPORT,'occlusion':'visible_rows_with_named_hidden_intervals'}

def covered(lo, hi, boxes):
    cursor = lo
    for a, b in sorted(boxes):
        if a > cursor + 1:
            break
        cursor = max(cursor, b)
        if cursor >= hi:
            return True
    return False


def image_pairs(data, native, roles, references, cap_references, lengths,body_references=None):
    """Native image connectivity does not depend on an endpoint clock."""
    from piu_timeline.play.skins.coverage import image_spans
    by_time = {f['playback_seconds']: f for f in native}
    width = data['analysis_width']
    spacing = (data['layout']['lanes'][1]['x'] - data['layout']['lanes'][0]['x']) * width
    proposals, heads, tails = [], defaultdict(set), defaultdict(set)
    for head, first in enumerate(data['notes']):
        if roles[head] != {'hold_start'}:
            continue
        before = dict(detection_points(first))
        regions=lane_regions(data,first['lane'])
        for tail, last in enumerate(data['notes']):
            if roles[tail] != {'hold_end'} or last['lane'] != first['lane']:
                continue
            after = dict(detection_points(last))
            proof, missing = [], []
            for time in sorted(before.keys() & after.keys()):
                a, b = before[time], after[time]
                if b <= a:
                    continue
                frame = by_time[time]
                center = data['layout']['lanes'][first['lane']]['x'] * width
                boxes = [span for o in frame.get('skin_observations', [])
                         if o['lane'] == first['lane'] and o['role'] in ('hold_start', 'hold_body', 'hold_end')
                         and not o.get('cap_subfeature')
                         and o['bounds_pixels'][0] <= center <= o['bounds_pixels'][2]
                         and o['bounds_pixels'][1] <= b and o['bounds_pixels'][3] >= a
                         for span in image_spans(o,references)]
                # Use only positively compared cap pixels of known endpoints.
                # Failed connection regions supply no coverage.
                boxes.extend(span for o in frame.get('skin_observations', [])
                             if o['lane']==first['lane'] and o['role']=='unknown'
                             and o.get('classification_status')=='cap_only'
                             and min(abs(o['y']*data['analysis_height']-a),abs(o['y']*data['analysis_height']-b))<1e-5
                             for span in image_spans(o,cap_references,cap_only=True))
                observed=coverage(a,b,boxes,regions)
                if observed is not None:
                    proof.append({'time': time, 'source_pts': frame['source_pts_seconds'], 'head_y': a, 'tail_y': b,**observed})
                else:
                    missing.append({'time': time, 'source_pts': frame['source_pts_seconds'],
                                    'failure_detail':'visible_hold_connection_unobserved'})
            if not supported(proof,spacing):
                continue
            gaps = [p['tail_y'] - p['head_y'] for p in proof]
            if max(gaps) - min(gaps) > 2 and lengths.check(head, tail)['status'] != 'consistent':
                continue
            proposals.append((head, tail, proof, missing)); heads[head].add(tail); tails[tail].add(head)
    from piu_timeline.play.skins.temporal import temporal_pairs
    existing={(head,tail):(proof,missing)for head,tail,proof,missing in proposals}
    temporal=temporal_pairs(data,native,roles,references,cap_references,length_checks=lengths,body_references=body_references)
    for pair in temporal['pairs']:
        head,tail=pair['head'],pair['tail']
        if (head,tail)in existing:
            proof,missing=existing[head,tail];times={p['time']for p in pair['proof']}
            proof[:]=sorted([*[p for p in proof if p['time']not in times or p.get('occluded_intervals')],*pair['proof']],key=lambda p:p['time'])
            missing.extend(pair['missing'])
        else:proposals.append((head,tail,pair['proof'],pair['missing']))
        heads[head].add(tail);tails[tail].add(head)
    for head,tail,proof,missing in proposals:
        for component in temporal['endpoint_components']:
            if not set(component['endpoint_notes'])<={head,tail}:continue
            if not any(p['body_template_support']for p in component['proof']):continue
            for point in component['proof']:
                observed={k:v for k,v in point.items()if k!='endpoint_observations'}
                for cap in point['endpoint_observations']:
                    observed['head_y'if cap['note']==head else'tail_y']=cap['y_pixels']
                proof.append(observed)
            missing.extend(component['missing'])
        proof.sort(key=lambda p:(p['time'],p.get('image_node',-1)))
        missing.sort(key=lambda p:p['time'])
    refuted={(p['head'],p['tail']):list(p['evidence'])for p in temporal['refuted']}
    positions=defaultdict(list)
    for i,note in enumerate(data['notes']):
        if note.get('duplicate_of')is not None or not roles[i]&{'tap','hold_start','hold_end'}:continue
        for time,y in detection_points(note):positions[time,note['lane']].append((i,y))
    for head,tail,proof,_ in proposals:
        first,last=data['notes'][head],data['notes'][tail]
        before,after=dict(detection_points(first)),dict(detection_points(last));seen=set()
        for point in proof:
            time=point['time'];bounds=point.get('covered_bounds_pixels')
            lo=before.get(time,bounds[0]if bounds else None);hi=after.get(time,bounds[1]if bounds else None)
            if lo is None or hi is None:continue
            for i,y in positions[time,first['lane']]:
                if i in(head,tail)or not lo<y<hi or(time,i)in seen:continue
                # A same-kind cap seen later can be an endpoint continuation.
                # Call it interior only while both endpoint positions are observed.
                if 'tap'not in roles[i]and(time not in before or time not in after):continue
                seen.add((time,i));refuted.setdefault((head,tail),[]).append({'time':time,'source_pts':point['source_pts'],
                    'source_note':i,'observed_roles':sorted(roles[i]),'trace':'frames.jsonl'})
    proposals=[p for p in proposals if p[:2]not in refuted]
    return proposals,[{'head':a,'tail':b,'evidence':proof}for(a,b),proof in refuted.items()]


def measure_connections(data,native,diagnostics,*,references=None,cap_references=None,body_references=None):
    from piu_timeline.play.skins.coverage import reference_rows
    if references is None and body_references is None:body_references=reference_rows(data,body_only=True)
    references=reference_rows(data)if references is None else references
    cap_references=reference_rows(data,cap_only=True)if cap_references is None else cap_references
    from piu_timeline.play.skins.extents import LengthChecks
    lengths = LengthChecks(data)
    records = observe(data, native)['notes']
    roles = {r['note']: {o['role'] for o in r['observations']} - {'unknown'} for r in records}
    proposals,refuted=image_pairs(data,native,roles,references,cap_references,lengths,body_references)
    heads,tails=defaultdict(set),defaultdict(set)
    for head,tail,_,_ in proposals:heads[head].add(tail);tails[tail].add(head)
    image_connections,represented=[],set()
    for head, tail, proof, missing in proposals:
        if len(heads[head]) != 1 or len(tails[tail]) != 1:
            continue
        first, last = data['notes'][head], data['notes'][tail]
        connection={'id':len(image_connections), 'lane': first['lane'], 'head_note': head, 'tail_note': tail,
                      'head_observation_note': head, 'tail_observation_note': tail,
                      'covered_notes': [head, tail], 'last_body_seconds': proof[-1]['time'],
                      'body_frames': len({p['time']for p in proof}),
                      'body_evidence': 'skin_temporal_image_regions'if any('covered_bounds_pixels'in p for p in proof)else'skin_start_body_end_images',
                      'source_pts_range': [proof[0]['source_pts'], proof[-1]['source_pts']],
                      'image_connection_evidence': proof,
                      'component_evidence': {str(i): {'kind': 'registered_cap',
                          'source_pts_seconds': sorted({p['source_pts'] for p in proof
                              if ('head_y'if i==head else'tail_y')in p})} for i in (head, tail)}}
        image_connections.append(connection)
        represented.update((head,tail))
        extent = lengths.cache.get((head, tail))
        if extent and extent['status'] == 'consistent':
            connection['endpoint_extent_evidence'] = extent
            unverified = extent['unverified_source_pts_seconds']
            unbound = extent['unregistered_playback_seconds']
            if unverified or unbound:
                diagnostics.append({'note': head, 'lane': first['lane'], 'image_connection_id':connection['id'], 'tail_note': tail,
                                    'reason': 'unresolved_hold_geometry',
                                    'failure_detail': 'known_hold_endpoint_extent_unregistered_frames',
                                    'visible_start_seconds': min(t for t, _ in first['points']),
                                    'visible_end_seconds': max(t for t, _ in last['points']),
                                    'observed_points': len(unverified)+len(unbound),
                                    'unregistered_source_pts_seconds': unverified,
                                    'unregistered_playback_seconds': unbound})
        if missing:
            diagnostics.append({'note': head, 'lane': first['lane'], 'reason': 'unresolved_hold_geometry',
                                'failure_detail': 'known_hold_image_connection_not_observed_in_clear_frames',
                                'image_connection_id':connection['id'], 'tail_note': tail,
                                'visible_start_seconds': missing[0]['time'],
                                'visible_end_seconds': missing[-1]['time'],
                                'observed_points': len({p['time']for p in missing}), 'image_evidence': missing})
    for pair in refuted:
        if pair['head']in represented and pair['tail']in represented:continue
        evidence=pair['evidence'];head=pair['head']
        diagnostics.append({'note':head,'lane':data['notes'][head]['lane'],'reason':'unresolved_hold_geometry',
                            'failure_detail':'skin_hold_interior_note_conflict','tail_note':pair['tail'],
                            'visible_start_seconds':min(p['time']for p in evidence),
                            'visible_end_seconds':max(p['time']for p in evidence),
                            'observed_points':len({p['time']for p in evidence}),'image_evidence':evidence})
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
    for hold in image_connections:
        for point in hold['image_connection_evidence']:
            spans=point.get('observed_intervals_pixels',
                            [point['covered_bounds_pixels']]if 'covered_bounds_pixels'in point else[(point['head_y'],point['tail_y'])])
            accounted[hold['lane'], point['time']].extend(spans)
    pending_bodies = defaultdict(list)
    for frame in native:
        for image in frame.get('skin_observations', []):
            owned=any(a <= image['y']*data['analysis_height'] <= b
                      for a,b in accounted[image['lane'],frame['playback_seconds']])
            if image['role'] == 'hold_body' and not owned and not image.get('cap_subfeature'):
                pending_bodies[image['lane']].append((frame['playback_seconds'], frame['source_pts_seconds'], image))
    for lane, observations in pending_bodies.items():
        diagnostics.append({'lane': lane, 'reason': 'unresolved_hold_geometry',
                            'failure_detail': 'skin_body_images_without_complete_endpoint_ownership',
                            'visible_start_seconds': observations[0][0], 'visible_end_seconds': observations[-1][0],
                            'observed_points': len(observations),
                            'image_evidence': [{'playback_seconds': t, 'source_pts_seconds': pts, 'trace':'frames.jsonl',
                                                **{k:image[k]for k in ('lane','x','y','role','template','bounds_pixels','region_errors')}}
                                               for t, pts, image in observations]})
    return image_connections
