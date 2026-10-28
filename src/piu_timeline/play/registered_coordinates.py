"""Acquisition object adapter for the TypeScript joint-coordinate solver."""
from piu_timeline.derived import CONTRACTS, call
FORMAT=CONTRACTS['registration']


def refine(motion,tracks,receptor,spacing,bottom):
    result=call('registration.refine',motion.samples,[{'lane':t.lane,'points':t.points}for t in tracks],receptor,spacing,bottom)
    apply_result(motion,tracks,result)


def apply_result(motion,tracks,result):
    for sample,updated in zip(motion.samples,result['samples'],strict=True):sample.update(updated)
    motion.coordinate_failures={int(i):r for i,r in result['coordinate_failures'].items()}
    motion.coordinate_conflicts=result['coordinate_conflicts']
    motion.coordinate_offsets={(id(tracks[i]),chunk):v for i,chunk,v in result['coordinate_offsets']}
    motion.coordinate_registration=result['coordinate_registration']
    motion.clocks={}
