"""TypeScript UCS hold simplification; recognition observations remain unchanged."""
from dataclasses import asdict
from piu_timeline.derived import CONTRACTS, call
POLICY=CONTRACTS['hold_simplification']


def continuous_state(runs,lane,bridge,origin):
    return call('chartHolds.continuousState',runs,lane,bridge,origin)


def simplify(document,observations,endpoints,notes,origin,held_runs=()):
    saved={f'{note},{edge}':v for (note,edge),v in endpoints.items()}
    result,edges,proof=call('chartHolds.simplify',asdict(document),observations,saved,notes,origin,held_runs)
    return result,{(int(k.split(',')[0]),k.split(',')[1]):v for k,v in edges.items()},proof
