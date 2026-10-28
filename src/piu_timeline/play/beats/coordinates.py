"""Python acquisition compatibility for the TypeScript native-coordinate stage."""
from piu_timeline.derived import CONTRACTS, call

FORMAT=CONTRACTS['coordinates']
RECOVERABLE_MOTION_FAILURES=('shared_timing_reconstruction_failed','shared_spacing_reconstruction_conflict')


def prepare(data,spacing,include_failed=False):
    result=call('coordinates.prepare',data,spacing,include_failed)
    if not result:return {}
    result['chunks']={int(k):{int(i):h for i,h in heads.items()}for k,heads in result['chunks'].items()}
    result['frames']={float(t):v for t,v in result['frames'].items()}
    result['observed']={int(i):set(times)for i,times in result['observed'].items()}
    result['reference_notes']=set(result['reference_notes'])
    return result


def fit(references,spacing):
    return call('coordinates.fit',references,spacing)


def predictions(a,b,notes,interval,support):
    return call('coordinates.predictions',a,b,notes,interval,support or None,FORMAT['reference_radius_seconds'])
