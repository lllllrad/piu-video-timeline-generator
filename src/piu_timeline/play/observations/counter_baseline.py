"""Preserve the pre-refinement counter readings independently of image evidence."""
from itertools import zip_longest
import json

from piu_timeline.play.observations.trace import stream_frames

BASELINE = 'frames.combo-baseline.jsonl'
LEGACY = 'frames.base.jsonl'
TRACE = 'frames.jsonl'
TIMES = ('source_pts_seconds', 'playback_seconds')
COUNTER = ('combo', 'combo_confidence', 'combo_read_mode')
FIELDS = (*TIMES, *COUNTER)


def baseline_path(directory):
    return next((directory/name for name in (BASELINE, LEGACY) if (directory/name).is_file()),
                directory/TRACE)


def save_baseline(directory, data=None):
    path = directory/BASELINE
    if path.is_file():
        return
    source = baseline_path(directory)
    # Older counter updates without a baseline may have left the original
    # observations in an atomic-build backup.
    if source == directory/TRACE and data and data.get('frame_observation_version', 2) >= 3:
        number = data.get('segment_number')
        if number is not None:
            for previous in sorted(directory.parent.glob(f'segment-{number:03}.previous-*/analysis.json')):
                saved = json.loads(previous.read_text())
                if (saved.get('frame_observation_version', 2) == 2
                        and all(saved.get(key) == data.get(key) for key in
                                ('media', 'start_seconds', 'end_seconds', 'analysis_width', 'layout'))
                        and (previous.parent/TRACE).is_file()):
                    source = previous.parent/TRACE
                    break
    staging = path.with_suffix('.pending')
    with stream_frames(source) as records, staging.open('w') as target:
        for frame in records:
            target.write(json.dumps({key: frame[key] for key in FIELDS if key in frame}) + '\n')
    staging.replace(path)


def baseline_frames(directory, *, full=False):
    with stream_frames(baseline_path(directory)) as baseline:
        if not full:
            for row in baseline:
                yield {key: row[key] for key in FIELDS if key in row}
            return
        with stream_frames(directory/TRACE) as frames:
            for frame, row in zip_longest(frames, baseline):
                if frame is None or row is None or any(frame[key] != row[key] for key in TIMES):
                    raise ValueError('Counter baseline differs from native frame timeline')
                for key in (*COUNTER, 'combo_recovered', 'combo_before_font_validation'):
                    frame.pop(key, None)
                frame.update({key: row[key] for key in COUNTER if key in row})
                yield frame
