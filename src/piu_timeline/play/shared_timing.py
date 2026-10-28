"""Reconstruct a shared displacement from registered native trajectory identities."""
from collections import defaultdict

import numpy as np

from piu_timeline.play.motion import ScrollMotion, LOCAL_CLOCK_FORMAT

FORMAT = {'schema':1,'revision':16,'method':'registered_peer_displacement','local_clock':LOCAL_CLOCK_FORMAT}


def registered_motion(tracks, timeline, height, spacing, receptor, bottom):
    """One saved-data call integrates and jointly registers every trajectory."""
    from piu_timeline.derived import call
    from piu_timeline.play.registered_coordinates import apply_result
    result=call('tracks.registered',[{'lane':t.lane,'points':t.points}for t in tracks],timeline,height,spacing,receptor,bottom)
    motion=ScrollMotion(height,spacing);motion.evidence_format=FORMAT
    motion.samples=result['samples'];motion.at_time={s['time']:s for s in motion.samples}
    motion.chunks=[]
    for sample in motion.samples:
        while len(motion.chunks)<=sample['chunk']:motion.chunks.append([])
        motion.chunks[sample['chunk']].append(sample)
    motion.registered_positions={float(t):{int(i):p for i,p in points.items()}for t,points in result['registered_positions'].items()}
    apply_result(motion,tracks,result)
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
    fitted_tracks=motion.fit_many(tracks,receptor,layout)
    for index,(note,track) in enumerate(zip(notes,tracks,strict=True)):
        # Short/noisy candidates already have explicit exclusion diagnostics.
        if len(track.points)<4 or track.points[-1][0]-track.points[0][0]<.065:
            continue
        fitted=fitted_tracks[index]
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
        previous={k:note.get(k) for k in ('target_seconds','prediction_uncertainty_seconds','fit_method',
                                         'native_clock_warning','crossing_method')}
        # Preliminary online fits do not own the final registered clock state.
        for key in ('native_clock_warning','crossing_method'):
            if not fitted or key not in fitted:note.pop(key,None)
        if fitted is None:
            visible=[motion.at_time[t] for t,y in track.points if receptor+.85*spacing<y<layout.get('note_y_max',.95)*height-.55*spacing]
            failure=motion.coordinate_failures.get(visible[-1]['chunk']) if visible else None
            failure=failure or 'insufficient_or_inconsistent_shared_motion'
            note.update(status='excluded',reason='shared_timing_reconstruction_failed',target_seconds=None,
                        timing_reconstruction={'status':'failed','reason':failure,
                                               'unaccepted_previous_estimate':previous})
            warnings.append({'note':index,'lane':track.lane,'reason':'shared_timing_reconstruction_failed',
                             'check':'timing_reconstruction','visible_start_seconds':track.points[0][0],
                             'visible_end_seconds':track.points[-1][0],'observed_points':len(track.points),
                             'failure_detail':failure})
        else:
            note.update(**fitted,timing_reconstruction={'status':'restored','format':FORMAT})
            if fitted.get('native_clock_warning'):
                warnings.append({'note':index,'lane':track.lane,'check':'timing_reconstruction',
                                 **fitted['native_clock_warning'],
                                 'visible_start_seconds':fitted['crossing_capture_range'][0],
                                 'visible_end_seconds':fitted['crossing_capture_range'][1],
                                 'crossing_source_pts_seconds':fitted['crossing_source_pts_seconds']})
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
