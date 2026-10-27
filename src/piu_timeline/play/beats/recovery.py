"""Recover a missing crossing clock from independently bracketed native heads."""
import math

from piu_timeline.charts.ucs import NATURAL_SPLITS
from piu_timeline.play.beats.coordinates import fit, FORMAT as COORDINATE_FORMAT

FORMAT={'schema':1,'revision':4,'method':'native_coordinates_with_frozen_beat_references',
        'rejected_beat_references':'unique_source_clock_rows_outside_tested_group',
        'measurement_limits':COORDINATE_FORMAT,'natural_splits':list(NATURAL_SPLITS)}


def direct_clock_rows(notes,groups,phase,phase_range):
    """Native-refined or recovered rows cannot prove a rejected group's target."""
    result=set()
    for i,note in enumerate(notes):
        beat=note.get('beat_reconstruction',{})
        if note['status']!='estimated'or beat.get('status')!='restored'or'group_index'not in beat:continue
        group=groups[beat['group_index']];index=group['notes'].index(i)
        domains=group.get('unconstrained_row_domains')
        if domains and domains[index][0]!=domains[index][1]:continue
        interval=note.get('video_target_range')
        if interval is None:continue
        target=note['target_seconds']
        if target+phase_range[0]-phase<interval[0]-1e-8 or target+phase_range[1]-phase>interval[1]+1e-8:continue
        result.add(i)
    return result


def candidate_window(note,notes,groups):
    """An old estimate selects references but never bounds the recovered time."""
    radius=COORDINATE_FORMAT['reference_radius_seconds']
    if note.get('reason')=='shared_timing_reconstruction_failed':
        seed=note.get('timing_reconstruction',{}).get('unaccepted_previous_estimate',{}).get('target_seconds')
        return (seed,[seed-radius,seed+radius],set())if seed is not None and math.isfinite(seed)else None
    beat=note.get('beat_reconstruction',{})
    rejected_domain=(note.get('reason')=='beat_timing_reconstruction_failed'and
                     beat.get('reason')in('native_coordinate_domains_incompatible','ambiguous_beat_rows'))
    rejected_geometry=note.get('reason')in('beat_grid_conflicts_with_spatial_spacing','beat_grid_conflicts_with_native_chord')
    if not((rejected_domain or rejected_geometry)and'group_index'in beat):return None
    omitted=set(groups[beat['group_index']]['notes'])
    intervals=[notes[i]['video_target_range']for i in omitted]
    seed=sum(note['video_target_range'])/2
    return seed,[min(v[0]for v in intervals)-radius,max(v[1]for v in intervals)+radius],omitted


def choose_row(models, sections, origin, phase,clock_range=None):
    lower=max(m['range'][0]for m in models);upper=min(m['range'][1]for m in models)
    if lower>upper:return {'status':'failed','reason':'incompatible_native_coordinate_models'}
    if clock_range is not None:
        lower=max(lower,clock_range[0]);upper=min(upper,clock_range[1])
        if lower>upper:return {'status':'failed','reason':'incompatible_native_and_clock_ranges'}
    for si,(lo,hi,bpm)in enumerate(sections):
        base=origin+lo+phase
        if not origin+lo<=lower<=upper<origin+hi:continue
        targets=[r['target_seconds']for m in models for r in m['model']['references']]
        for split in NATURAL_SPLITS:
            step=60/(bpm*split)
            if any(abs((t-base)/step-round((t-base)/step))>1e-6 for t in targets):continue
            a=math.ceil((lower-base)/step-1e-8);b=math.floor((upper-base)/step+1e-8)
            if a>b:continue
            if a<b:return {'status':'failed','reason':'ambiguous_native_coordinate_rows'}
            return {'status':'restored','section':si,'split':split,'row':a,
                    'target_seconds':base+a*step,'native_target_range':[lower,upper]}
        return {'status':'failed','reason':'native_coordinates_outside_natural_rows'}
    return {'status':'failed','reason':'native_coordinate_interval_crosses_tempo_boundary'}


def recover(notes, support, sections, origin, phase, alignment_error,groups=(),phase_range=None):
    """References are frozen before recovery; a rejected clock only locates a window."""
    if not support or phase is None:return {}
    frozen={i for i,n in enumerate(notes)if n['status']=='estimated'
            and n.get('beat_reconstruction',{}).get('status')=='restored'}
    direct=direct_clock_rows(notes,groups,phase,phase_range or[phase,phase])if groups else set()
    results={}
    for i,note in enumerate(notes):
        candidate=candidate_window(note,notes,groups)
        if candidate is None:continue
        seed,window,omitted=candidate
        eligible=direct-omitted if omitted else frozen
        section=next(((lo,hi)for lo,hi,_ in sections if origin+lo<=seed<origin+hi),None)
        if section is None:continue
        models=[]
        for number,heads in support['chunks'].items():
            if i not in heads:continue
            refs=[{'note':j,'target_seconds':notes[j]['target_seconds'],**head}for j,head in heads.items()
                  if j in eligible and window[0]<=notes[j]['target_seconds']<=window[1]
                  and origin+section[0]<=notes[j]['target_seconds']<origin+section[1]]
            model=fit(refs)
            if model is None:continue
            time=model['origin_seconds']+(heads[i]['offset']-model['offset_at_origin_pixels'])/model['velocity_pixels_per_second']
            error=(COORDINATE_FORMAT['maximum_native_error_pixels']+model['maximum_reference_error_pixels'])/model['velocity_pixels_per_second']
            lower,upper=model['reference_target_range']
            if not lower<=time-error<=time+error<=upper:continue
            models.append({'chunk':number,'head':heads[i],'model':model,'range':[time-error,time+error]})
        if not models:continue
        clock_range=note['video_target_range']if note.get('beat_reconstruction',{}).get('reason')=='ambiguous_beat_rows'else None
        result=choose_row(models,sections,origin,phase,clock_range)
        result.update(format=FORMAT,source_failure=note['reason'],reference_window_center_seconds=seed,models=models)
        if clock_range is not None:result['clock_constraint_range']=clock_range
        if omitted:result.update(excluded_reference_group=sorted(omitted),reference_selection='unique_source_clock_rows')
        results[i]=result
    # No recovered row can become a reference for another recovered row.
    for i,result in results.items():
        if result['status']!='restored':continue
        note=notes[i];target=result['target_seconds'];lower,upper=result['native_target_range']
        previous=note['timing_reconstruction']
        rejected={'rejected_beat_assignment':note['beat_reconstruction'],
                  'rejected_clock_target_range':note['video_target_range']}if note.get('reason')!='shared_timing_reconstruction_failed'else {}
        note.update(status='estimated',reason=None,target_seconds=target,
                    fit_method='native_beat_coordinate_interpolation',
                    prediction_uncertainty_seconds=max(target-lower,upper-target)+alignment_error,
                    video_target_range=[lower-alignment_error,upper+alignment_error],
                    beat_reconstruction={'status':'restored','method':FORMAT['method'],
                                         **{k:result[k]for k in ('section','split','row')}},
                    timing_reconstruction={'status':'restored','method':FORMAT['method'],
                                           'previous_motion_attempt':previous,**rejected})
    return results
