"""Check joint geometry before accepting independently timed neighboring tracks."""
from collections import defaultdict

import numpy as np


def spacing_failures(notes, spacing):
    at=defaultdict(list);pairs=defaultdict(list)
    for i,note in enumerate(notes):
        if note['status']!='estimated' or note.get('fit_method')=='isolated_native_track':continue
        for t,y in note['points']:at[t].append((y,i))
    for time,points in at.items():
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
        speed=(ca['velocity']+cb['velocity'])/2
        predicted=(second['target_seconds']-first['target_seconds'])*speed
        tolerance=max(1.,3*scatter)
        if abs(predicted-gap)<=tolerance+1e-6:continue
        for index in (a,b):
            failed.append({'note':index,'lane':notes[index]['lane'],'reason':'shared_spacing_reconstruction_conflict',
                           'check':'timing_reconstruction','visible_start_seconds':samples[0][0],
                           'visible_end_seconds':samples[-1][0],'observed_points':len(samples),
                           'peer_notes':[a,b],'observed_gap_pixels':gap,'reconstructed_gap_pixels':predicted,
                           'tolerance_pixels':tolerance})
    return failed
