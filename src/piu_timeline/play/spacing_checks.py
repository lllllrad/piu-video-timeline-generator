"""Compatibility adapters for TypeScript saved native-spacing checks."""
from piu_timeline.derived import CONTRACTS, call
SPACING_FORMAT=CONTRACTS['spacing']
CLOCK_CONVERSION_FORMAT=CONTRACTS['clock_conversion']


def attributed_heads(a,b,notes,models):
    rejected,proof=call('spacing.attributedHeads',a,b,notes,models)
    return tuple(rejected),proof


def registered_gap(first,second,samples,offsets,frames,a,b):
    grouped={}
    for (chunk,note),offset in offsets.items():grouped.setdefault(chunk,{})[note]=offset
    return call('spacing.registeredGap',first,second,samples,grouped,frames,a,b)


def clock_conversion(first,second):
    return call('spacing.clockConversion',first,second)


def spacing_failures(notes,spacing,motion=None,coordinate_support=None,diagnostics=None,baseline_indices=None,changed_indices=None):
    if motion is not None and hasattr(motion,'evidence'):motion=motion.evidence()
    return call('spacing.spacingFailures',notes,spacing,motion,coordinate_support or None,
                diagnostics,baseline_indices,changed_indices,mutated=(4,)if diagnostics is not None else ())
