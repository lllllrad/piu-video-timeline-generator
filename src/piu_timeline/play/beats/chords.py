"""Native chord evidence is calculated by the TypeScript saved-data stage."""
from piu_timeline.derived import CONTRACTS, call
FORMAT=CONTRACTS['chords']


def prepare(data,spacing):
    return call('chords.prepare',data,spacing)


def constrain(domains,step,constraints):
    options,proofs=call('chords.constrain',domains,step,constraints)
    return [tuple(d)for d in options],proofs


def conflicts(notes,constraints):
    return call('chords.conflicts',notes,constraints)
