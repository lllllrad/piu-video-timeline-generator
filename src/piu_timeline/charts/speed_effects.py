"""Translate measured speed transitions into reviewable chart metadata."""
import fcntl
from hashlib import sha256
import json

from piu_timeline.charts.gimmicks import validate_candidates
from piu_timeline.charts.official import write_json
from piu_timeline.charts.ucs import parse


def bpm_at(template, time):
    settings={};result=None
    starts={}
    for si,_,seconds in template.grid():starts.setdefault(si,float(seconds))
    for si,section in enumerate(template.sections):
        settings.update(section.directives)
        if starts[si]<=time:result=float(settings['BPM'])
    return result


def proposals(measured, metadata, timing_path, source):
    origin=metadata['alignment']['song_start_seconds']
    alignment_uncertainty=metadata['alignment'].get('uncertainty_seconds',0)
    template=parse(timing_path.read_text()) if timing_path.is_file() else None
    result=[]
    for change in measured['transitions']:
        if not change['auto_recordable']:continue
        start,end=change['start_seconds']-origin,change['end_seconds']-origin
        if not 0<=start<end:continue
        lo,hi=change['transition_range_seconds'];center=change['estimated_transition_seconds']
        # The nominal line intersection may sit just outside a capture bracket.
        # Retain the union, including one native frame of boundary uncertainty.
        cadence=(change['before']['end']-change['before']['start'])/(change['before']['frames']-1)
        bounds=[min(lo,center-cadence/2)-origin-alignment_uncertainty,max(hi,center+cadence/2)-origin+alignment_uncertainty]
        before,after=change['before'],change['after']
        bpm_before=bpm_at(template,(before['start']+before['end'])/2-origin) if template else None
        bpm_after=bpm_at(template,(after['start']+after['end'])/2-origin) if template else None
        context={'before':bpm_before,'after':bpm_after}
        if bpm_before and bpm_after:
            context.update(nominal_bpm_ratio=bpm_after/bpm_before,
                           measured_ratio_divided_by_bpm_ratio=change['speed_multiplier']/(bpm_after/bpm_before))
        proof={'source_id':source['source_id'],'segment_number':source['segment_number'],
               'playback_range':[change['start_seconds'],change['end_seconds']],
               'before':before,'after':after,'motion_chunk':change['motion_chunk'],
               'lane_spacing_pixels':change['lane_spacing_pixels'],'ucs_bpm_context':context,
               'song_alignment_uncertainty_seconds':alignment_uncertainty,
               'long_flank_confirmation':change['long_flank_confirmation']}
        key=f"{source['source_id']}:{source['segment_number']}:{center:.3f}"
        result.append({'id':'measured-speed-'+sha256(key.encode()).hexdigest()[:12],
            'kind':'scroll_speed_change','start_seconds':start,'end_seconds':end,
            'transition_range_seconds':bounds,'speed_multiplier':change['speed_multiplier'],
            'speed_ratio_range':change['speed_ratio_range'],'review_status':'pending',
            'reason':'Independent registered heads establish different stable velocities on both sides of this bounded transition. The measured ratio is not rounded to a presumed simple multiplier; UCS BPM context is retained separately.',
            'evidence':[proof]})
    return result


def record(repository, path, candidates):
    """Append native evidence without overwriting human review or typed values."""
    with (repository/'.chart-data.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        metadata=json.loads(path.read_text());existing=metadata.setdefault('gimmick_candidates',[])
        before=json.dumps(existing,sort_keys=True)
        for candidate in candidates:
            lo,hi=candidate['transition_range_seconds'];low,high=candidate['speed_ratio_range']
            owner=next((r for r in existing if r['kind']=='scroll_speed_change'
                        and r['transition_range_seconds'][0]<=hi and r['transition_range_seconds'][1]>=lo
                        and r['speed_ratio_range'][0]<=high and r['speed_ratio_range'][1]>=low),None)
            if owner is None:existing.append(candidate);continue
            proof=candidate['evidence'][0]
            identity=(proof['source_id'],proof['segment_number'],proof['before']['source_pts_seconds'],proof['after']['source_pts_seconds'])
            match=next((p for p in owner.setdefault('evidence',[])
                        if (p.get('source_id'),p.get('segment_number'),p.get('before',{}).get('source_pts_seconds'),
                            p.get('after',{}).get('source_pts_seconds'))==identity),None)
            if match is None:owner['evidence'].append(proof)
            elif 'long_flank_confirmation' not in match:
                match['long_flank_confirmation']=proof['long_flank_confirmation']
        validate_candidates(metadata)
        changed=before!=json.dumps(existing,sort_keys=True)
        if changed:write_json(path,metadata)
    return changed
