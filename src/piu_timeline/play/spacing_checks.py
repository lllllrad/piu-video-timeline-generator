"""Compatibility adapters for TypeScript saved native-spacing checks."""
from piu_timeline.derived import CONTRACTS, call
SPACING_FORMAT=CONTRACTS['spacing']
CLOCK_CONVERSION_FORMAT=CONTRACTS['clock_conversion']


def registered_gap(first,second,samples,offsets,frames,a,b):
    grouped={}
    for (chunk,note),offset in offsets.items():grouped.setdefault(chunk,{})[note]=offset
    return call('spacing.registeredGap',first,second,samples,grouped,frames,a,b)


def spacing_failures(notes,spacing,motion=None,coordinate_support=None,diagnostics=None,baseline_indices=None,changed_indices=None):
    if motion is not None and hasattr(motion,'evidence'):motion=motion.evidence()
    result=call('nativeCalls.spacingCheck',notes,spacing,motion,coordinate_support or None,
                baseline_indices,changed_indices,diagnostics is not None)
    if diagnostics is not None:diagnostics.extend(result['diagnostics'])
    return result['failures']
