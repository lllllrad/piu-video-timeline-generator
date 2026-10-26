"""Reconstruct a shared displacement from registered native trajectory identities."""
from collections import defaultdict

import numpy as np

from piu_timeline.play.motion import ScrollMotion

FORMAT = {'schema':1,'revision':11,'method':'registered_peer_displacement'}


def registered_motion(tracks, timeline, height, spacing, receptor, bottom):
    """Final identities remove repeated-pattern correspondence guesses."""
    at = defaultdict(dict)
    for index,track in enumerate(tracks):
        for time,y in track.points:
            if receptor+.85*spacing < y < bottom-.55*spacing:
                at[time][index]=(track.lane,y)
    motion=ScrollMotion(height,spacing)
    motion.evidence_format=FORMAT
    previous=None;anchor=None
    for native in timeline:
        time=native['time'];current=at[time]
        displacement=None;observed=None;support=lanes=0;scatter=0.;basis='unsupported'
        if previous is not None and 0 < time-previous['time'] <= .05+1e-6:
            before=at[previous['time']]
            pairs=[(before[i][1]-current[i][1],current[i][0],i) for i in before.keys() & current.keys()]
            if pairs:
                center=float(np.median([p[0] for p in pairs]));observed=center
                kept=[p for p in pairs if abs(p[0]-center)<=1.5]
                support=len(kept);lanes=len({p[1] for p in kept})
                if support>=2 and (lanes>=2 or max(current[p[2]][1] for p in kept)-min(current[p[2]][1] for p in kept)>.65*spacing) and -.75<=center<=spacing*30*(time-previous['time']):
                    displacement=max(0,float(np.median([p[0] for p in kept])))
                    scatter=max(.35,float(np.std([p[0] for p in kept])))
                    basis='independent_registered_peers'
                    anchor=(time,{p[2] for p in kept})
                elif (len(pairs)==1 and anchor is not None and time-anchor[0]<=.25+1e-6
                      and pairs[0][2] in anchor[1] and -.75<=pairs[0][0]<=spacing*30*(time-previous['time'])):
                    # A previously corroborated identity may carry the same
                    # coordinate system briefly. This is measured displacement,
                    # never interpolation across an absent source observation.
                    displacement=max(0,pairs[0][0]);support=lanes=1;scatter=.75
                    basis='registered_identity_continuation'
        if displacement is None:
            motion.chunks.append([]);phase=variance=0.;anchor=None
        else:
            phase=motion.samples[-1]['phase']+displacement
            variance=motion.samples[-1]['variance']+scatter**2
        sample={**native,'phase':phase,'pairwise_phase_pixels':phase,'observed_peer_displacement_pixels':observed,
                'variance':variance,'chunk':len(motion.chunks)-1,
                'support':support if displacement is not None else 0,'lanes':lanes if displacement is not None else 0,
                'displacement_basis':basis}
        motion.samples.append(sample);motion.at_time[time]=sample;motion.chunks[-1].append(sample)
        previous=native
    from piu_timeline.play.registered_coordinates import refine
    refine(motion,tracks,receptor,spacing,bottom)
    return motion


def restore(notes, tracks, timeline, layout, width, height):
    """A failed common reconstruction never silently becomes a local estimate."""
    spacing=float(np.median(np.diff([lane['x']*width for lane in layout['lanes']])))
    receptor=layout['receptor_y']*height
    motion=registered_motion(tracks,timeline,height,spacing,receptor,layout.get('note_y_max',.95)*height)
    motion.strict_clock=True
    shared_frames=defaultdict(dict)
    for i,track in enumerate(tracks):
        for t,y in track.points:shared_frames[t][i]=y
    warnings=list(motion.coordinate_conflicts)
    for index,(note,track) in enumerate(zip(notes,tracks,strict=True)):
        # Short/noisy candidates already have explicit exclusion diagnostics.
        if len(track.points)<4 or track.points[-1][0]-track.points[0][0]<.065:
            continue
        fitted=motion.fit(track,receptor,layout)
        peer_counts=defaultdict(int)
        for t,y in track.points:
            for peer,py in shared_frames[t].items():
                if peer!=index and (tracks[peer].lane!=track.lane or abs(py-y)>.65*spacing):
                    peer_counts[peer]+=1
        isolated = not any(count>=4 for count in peer_counts.values())
        if isolated and fitted is None:
            from piu_timeline.play.tracking import fit_track
            direct=fit_track(track,receptor,spacing)
            if direct['status']=='estimated':
                fitted={**direct,'fit_method':'isolated_native_track'}
        if fitted is None:
            visible=[motion.at_time[t] for t,y in track.points if receptor+.85*spacing<y<layout.get('note_y_max',.95)*height-.55*spacing]
            failure=motion.coordinate_failures.get(visible[-1]['chunk']) if visible else None
            failure=failure or 'insufficient_or_inconsistent_shared_motion'
            previous={k:note.get(k) for k in ('target_seconds','prediction_uncertainty_seconds','fit_method')}
            note.update(status='excluded',reason='shared_timing_reconstruction_failed',target_seconds=None,
                        timing_reconstruction={'status':'failed','reason':failure,
                                               'unaccepted_previous_estimate':previous})
            warnings.append({'note':index,'lane':track.lane,'reason':'shared_timing_reconstruction_failed',
                             'check':'timing_reconstruction','visible_start_seconds':track.points[0][0],
                             'visible_end_seconds':track.points[-1][0],'observed_points':len(track.points),
                             'failure_detail':failure})
        else:
            note.update(**fitted,timing_reconstruction={'status':'restored','format':FORMAT})
    from piu_timeline.play.spacing_checks import spacing_failures
    conflicts=spacing_failures(notes,spacing,motion)
    warnings.extend(conflicts)
    for record in conflicts:
        note=notes[record['note']]
        rejected={k:note.get(k) for k in ('target_seconds','prediction_uncertainty_seconds','fit_method')}
        note.update(status='excluded',reason=record['reason'],target_seconds=None,
                    timing_reconstruction={'status':'failed','reason':record['reason'],'unaccepted_previous_estimate':rejected})
    return motion,{'format':FORMAT,'status':'failed' if warnings else 'restored','warnings':warnings,
                   'restored_notes':sum(n.get('timing_reconstruction',{}).get('status')=='restored' for n in notes),
                   'failed_notes':len({r['note'] for r in warnings})}
