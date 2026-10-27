"""Recover a missing crossing clock from independently bracketed native heads."""
import math

from piu_timeline.charts.ucs import NATURAL_SPLITS
from piu_timeline.play.beats.coordinates import fit, FORMAT as COORDINATE_FORMAT

FORMAT={'schema':1,'method':'native_coordinates_with_frozen_beat_references',
        'measurement_limits':COORDINATE_FORMAT,'natural_splits':list(NATURAL_SPLITS)}


def choose_row(models, sections, origin, phase):
    lower=max(m['range'][0]for m in models);upper=min(m['range'][1]for m in models)
    if lower>upper:return {'status':'failed','reason':'incompatible_native_coordinate_models'}
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


def recover(notes, support, sections, origin, phase, alignment_error):
    """References are frozen before recovery; a rejected clock only locates a window."""
    if not support or phase is None:return {}
    frozen={i for i,n in enumerate(notes)if n['status']=='estimated'
            and n.get('beat_reconstruction',{}).get('status')=='restored'}
    results={}
    for i,note in enumerate(notes):
        if note.get('reason')!='shared_timing_reconstruction_failed':continue
        seed=note.get('timing_reconstruction',{}).get('unaccepted_previous_estimate',{}).get('target_seconds')
        if seed is None or not math.isfinite(seed):continue
        section=next(((lo,hi)for lo,hi,_ in sections if origin+lo<=seed<origin+hi),None)
        if section is None:continue
        models=[]
        for number,heads in support['chunks'].items():
            if i not in heads:continue
            radius=COORDINATE_FORMAT['reference_radius_seconds']
            refs=[{'note':j,'target_seconds':notes[j]['target_seconds'],**head}for j,head in heads.items()
                  if j in frozen and abs(notes[j]['target_seconds']-seed)<=radius
                  and origin+section[0]<=notes[j]['target_seconds']<origin+section[1]]
            model=fit(refs)
            if model is None:continue
            time=model['origin_seconds']+(heads[i]['offset']-model['offset_at_origin_pixels'])/model['velocity_pixels_per_second']
            error=(COORDINATE_FORMAT['maximum_native_error_pixels']+model['maximum_reference_error_pixels'])/model['velocity_pixels_per_second']
            lower,upper=model['reference_target_range']
            if not lower<=time-error<=time+error<=upper:continue
            models.append({'chunk':number,'head':heads[i],'model':model,'range':[time-error,time+error]})
        if not models:continue
        result=choose_row(models,sections,origin,phase)
        result.update(format=FORMAT,reference_window_center_seconds=seed,models=models)
        results[i]=result
    # No recovered row can become a reference for another recovered row.
    for i,result in results.items():
        if result['status']!='restored':continue
        note=notes[i];target=result['target_seconds'];lower,upper=result['native_target_range']
        previous=note['timing_reconstruction']
        note.update(status='estimated',reason=None,target_seconds=target,
                    fit_method='native_beat_coordinate_interpolation',
                    prediction_uncertainty_seconds=max(target-lower,upper-target)+alignment_error,
                    video_target_range=[lower-alignment_error,upper+alignment_error],
                    beat_reconstruction={'status':'restored','method':FORMAT['method'],
                                         **{k:result[k]for k in ('section','split','row')}},
                    timing_reconstruction={'status':'restored','method':FORMAT['method'],
                                           'previous_motion_attempt':previous})
    return results
