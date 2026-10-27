"""Check joint geometry before accepting independently timed neighboring tracks."""
from collections import defaultdict

import numpy as np
from piu_timeline.play.beats.coordinates import predictions
from piu_timeline.play.beats.coordinates import FORMAT as COORDINATE_FORMAT


def attributed_heads(a,b,notes,models):
    """Do not exclude an independently confirmed head for its neighbor's error."""
    if not models:return (a,b),[]
    rejected=set();proof=[]
    for model in models:
        if 'peer_offsets_pixels'not in model:return (a,b),[]
        errors=[offset-(model['offset_at_origin_pixels']+model['velocity_pixels_per_second']*
                       (notes[i]['target_seconds']-model['origin_seconds']))
                for i,offset in zip((a,b),model['peer_offsets_pixels'],strict=True)]
        tolerance=COORDINATE_FORMAT['maximum_native_error_pixels']+model['maximum_reference_error_pixels']
        bad=[i for i,error in zip((a,b),errors)if abs(error)>tolerance+1e-6]
        rejected.update(bad)
        proof.append({'chunk':model['chunk'],'peer_position_errors_pixels':errors,
                      'maximum_position_error_pixels':tolerance,'contradicting_notes':bad})
    # When only the relative gap contradicts the model, neither head has an
    # independent absolute verdict. Both remain unresolved in that case.
    return (tuple(i for i in(a,b)if i in rejected)if rejected else(a,b)),proof


def registered_gap(first,second,samples,offsets,frames,a,b):
    gaps=[]
    # Adjacency selects which gap needs checking, not which simultaneous
    # observations can prove its coordinate model. An intervening third head
    # cannot invalidate a measured pair inside that same source-time window.
    first_points=dict(first['points']);second_points=dict(second['points'])
    times=sorted(t for t in first_points.keys()&second_points.keys()
                 if samples[0][0]<=t<=samples[-1][0])
    for time in times:
        chunk=frames.get(time)
        if (chunk,a) in offsets and (chunk,b) in offsets:
            gaps.append((time,offsets[chunk,b]-offsets[chunk,a]))
    if len(gaps)<4 or gaps[-1][0]-gaps[0][0]<.065:return None
    corrections=[]
    for note in (first,second):
        clock=note.get('motion_clock',{})
        if not all(key in clock for key in ('origin','velocity','intercept')) or 'motion_target_phase' not in note:return None
        original=clock['origin']+(note.get('clock_target_phase',note['motion_target_phase'])-clock['intercept'])/clock['velocity']
        corrections.append((note['target_seconds']-original)*clock['velocity'])
    return float(np.median([gap for _,gap in gaps]))+corrections[1]-corrections[0]


def spacing_failures(notes, spacing, motion=None, coordinate_support=None, diagnostics=None, baseline_indices=None):
    if motion is not None and hasattr(motion,'evidence'):motion=motion.evidence()
    offsets={(record['chunk'],head['note']):head['offset_pixels']
             for record in (motion or {}).get('coordinate_registration',{}).get('chunks',[]) if record.get('status')=='fitted'
             for head in record.get('head_offsets',[])}
    frames={sample['time']:sample['chunk']for sample in (motion or {}).get('samples',[])}
    at=defaultdict(list);pairs=defaultdict(list)
    for i,note in enumerate(notes):
        if note['status']!='estimated' or note.get('fit_method')=='isolated_native_track':continue
        for t,y in note['points']:at[t].append((y,i))
    for time,points in sorted(at.items()):
        points.sort()
        neighbors=list(zip(points,points[1:]))
        if baseline_indices is not None:
            baseline=[p for p in points if p[1]in baseline_indices]
            neighbors.extend(pair for pair in zip(baseline,baseline[1:])if pair not in neighbors)
        for (ya,a),(yb,b) in neighbors:
            if yb-ya>.65*spacing:pairs[(a,b)].append((time,yb-ya))
    failed=[]
    for (a,b),samples in pairs.items():
        if len(samples)<4 or samples[-1][0]-samples[0][0]<.065:continue
        first,second=notes[a],notes[b]
        ca,cb=first.get('motion_clock'),second.get('motion_clock')
        gaps=np.array([gap for _,gap in samples]);gap=float(np.median(gaps))
        scatter=float(np.median(abs(gaps-gap)))
        if scatter>1.5:continue
        if motion is None:
            predicted=((second['target_seconds']-first['target_seconds'])*ca['velocity'] if ca and cb and ca==cb else None)
        else:
            predicted=registered_gap(first,second,samples,offsets,frames,a,b)if ca and cb else None
        models=predictions(a,b,notes,(samples[0][0],samples[-1][0]),coordinate_support)
        if models:
            # A model is selected by independent reference support, regardless
            # of its verdict. Any supported disagreement must remain a failure.
            predicted=max(models,key=lambda m:abs(m['predicted_gap_pixels']-gap))['predicted_gap_pixels']
            if diagnostics is not None:diagnostics.append({'peer_notes':[a,b],'observed_gap_pixels':gap,'models':models})
        elif not ca or not cb:continue
        tolerance=max(1.,3*scatter)
        if predicted is not None and abs(predicted-gap)<=tolerance+1e-6:continue
        rejected,attribution=attributed_heads(a,b,notes,models)
        for index in rejected:
            failed.append({'note':index,'lane':notes[index]['lane'],'reason':'shared_spacing_reconstruction_conflict' if predicted is not None else 'shared_spacing_model_unavailable',
                           'check':'timing_reconstruction','visible_start_seconds':samples[0][0],
                           'visible_end_seconds':samples[-1][0],'observed_points':len(samples),
                           'peer_notes':[a,b],'observed_gap_pixels':gap,'reconstructed_gap_pixels':predicted,
                           'tolerance_pixels':tolerance,**({'independent_coordinate_models':models,
                           'native_position_attribution':attribution}if models else {})})
    return failed
