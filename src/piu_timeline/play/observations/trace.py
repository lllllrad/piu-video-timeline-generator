"""Bounded-memory views of retained JSONL observations, preserving every field."""
from contextlib import contextmanager
import json


@contextmanager
def stream_frames(path, expected_count=None, *, comparisons=False):
    """Validate completeness when the sequential consumer exhausts its input."""
    from piu_timeline.play.observations.skin_results import restore
    with path.open() as source:
        def records():
            count = 0
            for line in source:
                count += 1
                frame = json.loads(line)
                yield restore(frame,path.parent) if comparisons else frame
            if expected_count is not None and count != expected_count:
                raise ValueError('Native observation frame counts differ')
        yield records()
