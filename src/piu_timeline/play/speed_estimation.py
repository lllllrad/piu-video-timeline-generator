"""Compatibility adapter for TypeScript measured scroll-speed proposals."""
from piu_timeline.derived import CONTRACTS, call
FORMAT=CONTRACTS['speed']


def window(samples,spacing):return tuple(call('speed.window',samples,spacing))


def transition(before,after,samples,spacing):
    return call('speed.transition',before,after,samples,spacing)


def estimate(data):return call('speed.estimate',data)
