"""Check joint geometry before accepting independently timed neighboring tracks."""
from collections import defaultdict

import numpy as np


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


def spacing_failures(notes, spacing, motion=None):
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
        for (ya,a),(yb,b) in zip(points,points[1:]):
            if yb-ya>.65*spacing:pairs[(a,b)].append((time,yb-ya))
    failed=[]
    for (a,b),samples in pairs.items():
        if len(samples)<4 or samples[-1][0]-samples[0][0]<.065:continue
        first,second=notes[a],notes[b]
        ca,cb=first.get('motion_clock'),second.get('motion_clock')
        if not ca or not cb:continue
        gaps=np.array([gap for _,gap in samples]);gap=float(np.median(gaps))
        scatter=float(np.median(abs(gaps-gap)))
        if scatter>1.5:continue
        if motion is None:
            predicted=((second['target_seconds']-first['target_seconds'])*ca['velocity'] if ca==cb else None)
        else:
            predicted=registered_gap(first,second,samples,offsets,frames,a,b)
        tolerance=max(1.,3*scatter)
        if predicted is not None and abs(predicted-gap)<=tolerance+1e-6:continue
        for index in (a,b):
            failed.append({'note':index,'lane':notes[index]['lane'],'reason':'shared_spacing_reconstruction_conflict' if predicted is not None else 'shared_spacing_model_unavailable',
                           'check':'timing_reconstruction','visible_start_seconds':samples[0][0],
                           'visible_end_seconds':samples[-1][0],'observed_points':len(samples),
                           'peer_notes':[a,b],'observed_gap_pixels':gap,'reconstructed_gap_pixels':predicted,
                           'tolerance_pixels':tolerance})
    return failed
