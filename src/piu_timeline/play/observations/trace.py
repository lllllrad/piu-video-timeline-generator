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


WORKSPACE = 'frame-workspace.json'


def retired(directory):
    return (directory/WORKSPACE).is_file()


def retire(directory):
    """Remove temporary frames and comparisons from a completed pending build."""
    import re
    import shutil
    from piu_timeline.play.observations.artifacts import save_input

    if not re.fullmatch(r'segment-\d{3,}\.build-[a-f0-9]+', directory.name):
        raise ValueError('Frame retirement requires an unpublished segment build')
    if not all((directory/name).is_file() for name in ('coordinates.json', 'report-data.json', 'report.html')):
        raise ValueError('Frame retirement requires completed coordinates and report')
    comparisons = directory/'comparison-evidence'
    if comparisons.is_dir():
        shutil.rmtree(comparisons)
    (directory/'frames.jsonl').unlink(missing_ok=True)
    save_input(directory/WORKSPACE, {'schema': 1, 'state': 'retired'})
