"""Compatibility adapter for the TypeScript bounded common-phase model."""
from piu_timeline.derived import call


def fit_groups(groups,phase,consistent_notes=None):
    return call('phase.fitGroups',groups,phase,callback=consistent_notes)


def fit_phase(groups,uncertainty,consistent_notes=None):
    return call('phase.fitPhase',groups,uncertainty,callback=consistent_notes)
