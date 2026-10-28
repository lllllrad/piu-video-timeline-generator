"""Compatibility adapter for TypeScript native timing validation."""
from piu_timeline.derived import call


def validate(data,notes,spacing,support,baseline_indices=None,changed_indices=None):
    return call('validation.validate',data,notes,spacing,support or None,baseline_indices,changed_indices,mutated=(1,))
