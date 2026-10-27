"""Reviewable chart effects with scoped provisional processing rules."""
import fcntl
from hashlib import sha256
import json
import math
from pathlib import Path

from piu_timeline.charts.official import write_json


def validate_candidates(metadata):
    candidates = metadata.get('gimmick_candidates', [])
    if not isinstance(candidates,list):
        raise ValueError('Gimmick candidates must be a list')
    identifiers = set()
    for record in candidates:
        if (not isinstance(record,dict) or not isinstance(record.get('id'),str) or not record['id'].strip()
                or record['id'] in identifiers or record.get('review_status') not in ('pending','confirmed','rejected')
                or not isinstance(record.get('reason'),str) or not record['reason'].strip()
                or not isinstance(record.get('kind'),str) or not record['kind'].strip()):
            raise ValueError('Malformed gimmick candidate identity, reason or review status')
        start,end = record.get('start_seconds'),record.get('end_seconds')
        if (any(isinstance(t,bool) or not isinstance(t,(int,float)) or not math.isfinite(t) for t in (start,end))
                or not 0 <= start < end or not isinstance(record.get('evidence',[]),list)):
            raise ValueError('Gimmick candidates require finite increasing song times and an evidence list')
        increment = record.get('combo_increment')
        if record['kind']=='decorative_note_art':
            bounds=record.get('game_image_bounds');error=record.get('boundary_uncertainty_seconds')
            if (record.get('note_semantics')!='decorative_non_playable' or record.get('playable_notes_present')is not False
                    or not isinstance(record.get('display_content'),str) or not record['display_content'].strip()
                    or not isinstance(bounds,list) or len(bounds)!=4
                    or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v)for v in bounds)
                    or not (0<=bounds[0]<bounds[0]+bounds[2]<=1 and 0<=bounds[1]<bounds[1]+bounds[3]<=1)
                    or isinstance(error,bool) or not isinstance(error,(int,float)) or not math.isfinite(error) or not 0<=error<=.1):
                raise ValueError('Decorative artwork requires non-playable semantics, a scope without playable notes, normalized bounds and bounded time uncertainty')
        if record['kind'] == 'suspected_multi_increment' and (type(increment) is not int or not 2 <= increment <= 10):
            raise ValueError('Multi-increment effects require an integer combo_increment from 2 to 10')
        if record['kind']=='scroll_pause':
            duration=record.get('pause_duration_seconds')
            uncertainty=record.get('boundary_uncertainty_seconds')
            if (record.get('speed_multiplier')!=0 or isinstance(record.get('speed_multiplier'),bool)
                    or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (duration,uncertainty))
                    or abs(duration-(end-start))>1e-6 or not 0<=uncertainty<=.1):
                raise ValueError('Scroll pauses require zero speed, matching duration and bounded boundary uncertainty')
        if record['kind']=='scroll_speed_change':
            ratio=record.get('speed_multiplier');bounds=record.get('speed_ratio_range');transition=record.get('transition_range_seconds')
            if (isinstance(ratio,bool) or not isinstance(ratio,(int,float)) or not math.isfinite(ratio) or ratio<=0
                    or any(not isinstance(a,list) or len(a)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float))
                           or not math.isfinite(v) for v in a) for a in (bounds,transition))):
                raise ValueError('Speed changes require a positive measured ratio and finite two-element ranges')
            if not (0<bounds[0]<=ratio<=bounds[1] and not bounds[0]<=1<=bounds[1]
                    and start<=transition[0]<=transition[1]<=end):
                raise ValueError('Speed ratio bounds must exclude one and the transition must lie inside the effect')
        identifiers.add(record['id'])
    pauses=sorted([r for r in candidates if r['kind']=='scroll_pause' and r['review_status']!='rejected'],key=lambda r:r['start_seconds'])
    if any(a['end_seconds']>b['start_seconds'] for a,b in zip(pauses,pauses[1:])):
        raise ValueError('Active scroll pauses cannot overlap')
    return candidates


def known_origin(data, output, metadata):
    """Use verified existing translations; never guess a song offset."""
    identity = data.get('media',{})
    source = metadata.get('source',{})
    if (source.get('source_id') == output.parents[1].name
            and source.get('segment_number') == data.get('segment_number')
            and source.get('media_size_bytes') == identity.get('size_bytes')
            and source.get('media_mtime_ns') == identity.get('mtime_ns')):
        return metadata.get('alignment',{}).get('song_start_seconds')
    cache = output/'chart-policy-alignment.json'
    if cache.is_file():
        saved = json.loads(cache.read_text());contract = saved.get('contract',{})
        if (contract.get('media') == identity and contract.get('start_seconds') == data['start_seconds']
                and contract.get('end_seconds') == data['end_seconds']):
            return saved.get('alignment',{}).get('song_start_seconds')
    return None


def visibility_evidence_key(proof):
    """Native frame identity, independent of fit noise or transient track IDs."""
    keys=('source_id','segment_number','lanes','loss_source_pts_ranges')
    if not isinstance(proof,dict) or not all(key in proof for key in keys):
        return json.dumps(proof,sort_keys=True)
    frames=sorted([round(value,6) for value in interval] for interval in proof['loss_source_pts_ranges'])
    return json.dumps([proof['source_id'],proof['segment_number'],sorted(proof['lanes']),frames])


def distinct_visibility_evidence(records):
    seen=set();result=[]
    for record in records:
        key=visibility_evidence_key(record)
        if key not in seen:
            result.append(record);seen.add(key)
    return result


def record_candidates(data, output, registration):
    """Append conservative visibility-effect candidates without changing UCS/policy."""
    boundaries = data.get('visual_channels',{}).get('processing',{}).get('visibility_boundaries',[])
    if not boundaries:
        return {'status':'none','changed':False}
    output = Path(output)
    metadata_path = Path(registration['chart']).with_name('metadata.json')
    repository = Path(registration['repository'])
    with (repository/'.chart-data.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        metadata = json.loads(metadata_path.read_text())
        candidates = validate_candidates(metadata)
        origin = known_origin(data,output,metadata)
        if not isinstance(origin,(int,float)) or isinstance(origin,bool) or not math.isfinite(origin):
            pending = {'status':'song_alignment_required','boundaries':boundaries}
            write_json(output/'gimmick-candidates.json',pending)
            return {**pending,'changed':False}
        before = json.dumps(candidates,sort_keys=True)
        processing = {r['note']:r for r in data['visual_channels']['processing']['notes']}
        for boundary in boundaries:
            lo,hi = boundary['playback_range'];start,end = lo-origin,hi-origin
            if not 0 <= start < end:
                continue
            kind = 'suspected_visibility_modifier'
            match = next((r for r in candidates if r['kind']==kind and
                          min(end,r['end_seconds'])-max(start,r['start_seconds']) >= .8*min(end-start,r['end_seconds']-r['start_seconds'])),None)
            if match is None:
                key = f'{kind}:{start:.1f}:{end:.1f}'
                match = {'id':'suspected-'+sha256(key.encode()).hexdigest()[:12], 'kind':kind,
                         'start_seconds':start,'end_seconds':end,'review_status':'pending',
                         'reason':'Heads repeatedly disappear at a stable height before the receptor across several lanes. A chart visibility effect is suspected; capture, overlay or calibration causes remain possible.',
                         'evidence':[]}
                candidates.append(match)
            proof = {'source_id':output.parents[1].name,'segment_number':data.get('segment_number'),
                     'playback_range':[lo,hi], 'notes':boundary['notes'],
                     'lanes':sorted({data['notes'][n]['lane'] for n in boundary['notes']}),
                     'last_visible_height_spacing':boundary['last_visible_height_spacing'],
                     'loss_source_pts_ranges':[processing[n]['visibility_loss']['source_pts_seconds'] for n in boundary['notes']]}
            evidence=distinct_visibility_evidence(match.setdefault('evidence',[]))
            if visibility_evidence_key(proof) not in {visibility_evidence_key(item) for item in evidence}:
                evidence.append(proof)
            match['evidence']=evidence
        changed = before != json.dumps(candidates,sort_keys=True)
        if changed:
            metadata['gimmick_candidates'] = candidates
            write_json(metadata_path,metadata)
    result = {'status':'recorded','changed':changed,'metadata':str(metadata_path),
              'candidates':[r['id'] for r in candidates]}
    write_json(output/'gimmick-candidates.json',result)
    return result
