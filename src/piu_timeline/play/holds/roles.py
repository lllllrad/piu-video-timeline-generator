"""Source-role adapters for TypeScript hold cap ownership."""
from piu_timeline.derived import call,projection_input


def observed_tail_roles(data):
    return call('holdProjection.observedTailRoles',projection_input(data))
