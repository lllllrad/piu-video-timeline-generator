"""Timing-range view adapters; TypeScript consumes retained visual evidence."""
import json
from piu_timeline.derived import call,evidence_input


def counter_frame_ranges(path):
    from piu_timeline.play.observations.records import counter
    with path.open()as stream:frames=[counter(json.loads(line))for line in stream]
    return call('ranges.counterFrameRanges',frames)


def timing_ranges(data):
    result=call('ranges.timingRanges',evidence_input(data))
    result['notes']={int(i):v for i,v in result['notes'].items()}
    return result
