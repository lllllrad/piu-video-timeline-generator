"""Compatibility adapter for native registered-coordinate block transfer."""
from piu_timeline.derived import call


def crossing(motion,sample,phase,error):
    return call('clocks.bridge',motion._state(),sample,phase,error)
