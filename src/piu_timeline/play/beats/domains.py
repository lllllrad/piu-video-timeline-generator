"""Compatibility adapter for TypeScript beat-row domain intersection."""
from piu_timeline.derived import CONTRACTS, call
FORMAT=CONTRACTS['domains']


def constrain(options,step,origin,blocks):
    rows,proofs=call('domains.constrain',options,step,origin,blocks)
    return [tuple(d)for d in rows],proofs
