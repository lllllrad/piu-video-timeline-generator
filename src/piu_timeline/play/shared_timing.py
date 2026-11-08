"""Reconstruct a shared displacement from registered native trajectory identities."""

import numpy as np
from piu_timeline.derived import CONTRACTS, call

from piu_timeline.play.motion import ScrollMotion

FORMAT = CONTRACTS['shared_motion']


def registered_motion(tracks, timeline, height, spacing, receptor, bottom):
    """One saved-data call integrates and jointly registers every trajectory."""
    from piu_timeline.derived import call
    from piu_timeline.play.registered_coordinates import apply_result
    result=call('tracks.registered',[{'lane':t.lane,'points':t.points,
                'coordinate_basis':getattr(t,'coordinate_basis',None),
                'registration_uncertainty_pixels':getattr(t,'registration_uncertainty_pixels',0)}for t in tracks],
                timeline,height,spacing,receptor,bottom)
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
    """Native-object adapter; all physical calculations run in one TypeScript call."""
    result=call('physicalTiming.solve',{'notes':notes,'frame_timeline':timeline,'layout':layout,
                                     'analysis_width':width,'analysis_height':height},
        [{'note_index':i,'lane':t.lane,'points':t.points,
          'coordinate_basis':getattr(t,'coordinate_basis',None),
          'registration_uncertainty_pixels':getattr(t,'registration_uncertainty_pixels',0)}for i,t in enumerate(tracks)])
    notes[:]=result['notes']
    from piu_timeline.play.registered_coordinates import apply_result
    spacing=float(np.median(np.diff([l['x']*width for l in layout['lanes']])))
    motion=ScrollMotion(height,spacing);motion.evidence_format=FORMAT
    motion.samples=result['motion_state']['samples']
    motion.at_time={s['time']:s for s in motion.samples}
    motion.registered_positions={float(t):{int(i):v for i,v in points.items()}
                                 for t,points in result['motion_state']['registered_positions'].items()}
    apply_result(motion,tracks,result['motion_state'])
    return motion,result['timing_reconstruction']
