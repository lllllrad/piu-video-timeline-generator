"""Compatibility adapter for TypeScript native-coordinate row recovery."""
from piu_timeline.derived import CONTRACTS, call
FORMAT=CONTRACTS['recovery']


def direct_clock_rows(notes,groups,phase,phase_range):
    return set(call('recovery.directClockRows',notes,groups,phase,phase_range))


def candidate_window(note,notes,groups):
    result=call('recovery.candidateWindow',note,notes,groups)
    return (result[0],result[1],set(result[2]))if result else None


def choose_row(models,sections,origin,phase,clock_range=None):
    return call('recovery.chooseRow',models,sections,origin,phase,clock_range)


def interpolation_models(index,notes,support,eligible,section,origin,window=None):
    return call('recovery.interpolationModels',index,notes,support,eligible,section,origin,window)


def block_validation(index,result,notes,support,spacing,motion,native_chords):
    return call('recovery.blockValidation',index,result,notes,support,spacing,motion,native_chords)


def recover(notes,support,sections,origin,phase,alignment_error,groups=(),phase_range=None,spacing=None,motion=None,native_chords=()):
    result=call('recovery.recover',notes,support or None,sections,origin,phase,alignment_error,
                groups,phase_range,spacing,motion,native_chords,mutated=(0,))
    return {int(i):r for i,r in result.items()}
