"""Validate musical spacing from independent native head measurements."""
from itertools import combinations

import numpy as np

RECOVERABLE_MOTION_FAILURES=('shared_timing_reconstruction_failed','shared_spacing_reconstruction_conflict')

FORMAT={'schema':1,'revision':8,'minimum_references':5,'minimum_lanes':2,
        'reference_radius_seconds':.75,'minimum_target_span_seconds':.3,
        'minimum_slope_span_seconds':.15,'maximum_reference_error_pixels':1.,
        'maximum_native_error_pixels':1.5}


def prepare(data,spacing,include_failed=False):
    """Freeze native support before testing beat candidates, without input evidence."""
    motion=data.get('scroll_motion',{});samples={s['time']:s for s in motion.get('samples',[])}
    observed={r['note']:{s['time']for s in r['observations']if s.get('native_cap_registration_status')!='conflicting'}
              for r in data.get('head_registration',{}).get('notes',[])
              if r['status']=='registered'or r.get('coordinate_method')in('native_cap_measurements','native_image_anchors')}
    if not observed:return {}
    height=data['analysis_height'];receptor=data['layout']['receptor_y']*height
    bottom=data['layout'].get('note_y_max',.95)*height;chunks={}
    for record in motion.get('coordinate_registration',{}).get('chunks',[]):
        if record['status']!='fitted':continue
        number=record['chunk'];heads={}
        for head in record['head_offsets']:
            index=head['note']
            if index not in observed:continue
            note=data['notes'][index]
            if note['status']!='estimated'and not(include_failed and note.get('reason')in
                    (*RECOVERABLE_MOTION_FAILURES,'beat_timing_reconstruction_failed',
                     'beat_grid_conflicts_with_spatial_spacing','beat_grid_conflicts_with_native_chord')):continue
            points=[(t,y)for t,y in note['points']if t in observed[index]and t in samples
                    and samples[t]['chunk']==number and receptor+.85*spacing<y<bottom-.55*spacing]
            if len(points)<4 or points[-1][0]-points[0][0]<.065:continue
            error=max(abs(y+samples[t]['phase']-head['offset_pixels'])for t,y in points)
            if error>FORMAT['maximum_native_error_pixels']:continue
            heads[index]={'offset':head['offset_pixels'],'lane':note['lane'],
                          'native_points':len(points),'native_maximum_error_pixels':error,
                          'source_pts_range':[samples[points[0][0]]['source_pts'],samples[points[-1][0]]['source_pts']]}
        chunks[number]=heads
    return {'chunks':chunks,'frames':{t:s['chunk']for t,s in samples.items()},'observed':observed,
            'reference_notes':{i for i,n in enumerate(data['notes'])if n['status']=='estimated'}}


def fit(references):
    """Every reference must agree; a robust estimate cannot discard an outlier."""
    if len(references)<FORMAT['minimum_references']or len({r['lane']for r in references})<FORMAT['minimum_lanes']:return None
    targets=np.array([r['target_seconds']for r in references]);offsets=np.array([r['offset']for r in references])
    if len(set(targets))<3 or max(targets)-min(targets)<FORMAT['minimum_target_span_seconds']:return None
    slopes=[(offsets[j]-offsets[i])/(targets[j]-targets[i])for i,j in combinations(range(len(references)),2)
            if abs(targets[j]-targets[i])>=FORMAT['minimum_slope_span_seconds']]
    if not slopes:return None
    velocity=float(np.median(slopes));origin=float(min(targets))
    intercept=float(np.median(offsets-velocity*(targets-origin)))
    error=float(max(abs(offsets-velocity*(targets-origin)-intercept)))
    if velocity<=0 or error>FORMAT['maximum_reference_error_pixels']:return None
    return {'velocity_pixels_per_second':velocity,'origin_seconds':origin,'offset_at_origin_pixels':intercept,
            'maximum_reference_error_pixels':error,'reference_target_range':[origin,float(max(targets))],
            'references':references}


def predictions(a,b,notes,interval,support):
    """Leave the tested pair out and interpolate only inside independent anchors."""
    if not support:return []
    ta,tb=notes[a]['target_seconds'],notes[b]['target_seconds']
    common=(dict(notes[a]['points']).keys()&dict(notes[b]['points']).keys()
            &support['observed'].get(a,set())&support['observed'].get(b,set()))
    models=[]
    for number,heads in support['chunks'].items():
        if a not in heads or b not in heads:continue
        times=sorted(t for t in common if interval[0]<=t<=interval[1]and support['frames'].get(t)==number)
        if len(times)<4 or times[-1]-times[0]<.065:continue
        refs=[{'note':i,'target_seconds':notes[i]['target_seconds'],**head}for i,head in heads.items()
              if i not in (a,b)and i in support['reference_notes']and notes[i]['status']=='estimated'
              and min(ta,tb)-FORMAT['reference_radius_seconds']<=notes[i]['target_seconds']<=max(ta,tb)+FORMAT['reference_radius_seconds']]
        reference_sets=[refs]
        for proof in support.get('recovery_reference_sets',()):
            if proof['chunk']!=number or proof['note']not in(a,b):continue
            original=proof['references']
            if any(r['note']not in support['reference_notes']or notes[r['note']]['status']!='estimated'
                   or notes[r['note']]['target_seconds']!=r['target_seconds']for r in original):continue
            reference_sets.append([r for r in original if r['note']not in(a,b)])
        seen=set()
        for refs in reference_sets:
            key=tuple(sorted(r['note']for r in refs))
            if key in seen:continue
            seen.add(key);model=fit(refs)
            if model is None:continue
            lo,hi=model['reference_target_range']
            if not lo<=min(ta,tb)<=max(ta,tb)<=hi:continue
            models.append({'chunk':number,'predicted_gap_pixels':model['velocity_pixels_per_second']*(tb-ta),
                           'peer_offsets_pixels':[heads[a]['offset'],heads[b]['offset']],
                           'coobserved_points':len(times),'visible_range':[times[0],times[-1]],**model})
    return models
