"""Adapters for TypeScript review candidate constraints."""
from piu_timeline.derived import call,evidence_input
EARLY_SECONDS=.25
LATE_SECONDS=.5


def target_offsets(data,local_offset):
    return call('candidates.targetOffsets',{'display_delay_correction_ms':data.get('display_delay_correction_ms',0)},local_offset)


def target_in_window(note,lo,hi,offset):
    return call('candidates.targetInWindow',note,lo,hi,offset)


def association_window(note,correction=0):
    return call('candidates.associationWindow',note,correction)


def intersect_window(interval,window):
    return call('candidates.intersectWindow',interval,window)


def candidates(data,events):
    result,rejected=call('candidates.candidates',evidence_input(data),events)
    return {int(i):v for i,v in result.items()},{int(i):v for i,v in rejected.items()}
