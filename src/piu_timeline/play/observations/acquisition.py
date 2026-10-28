"""Explicit source-media entry point for hold, receptor and appearance features."""
import json


def hold_observations(data, directory):
    from piu_timeline.play.holds.features import acquire_features
    from piu_timeline.play.receptors import observations, reject_common_flashes
    acquire_features(data, directory)
    with (directory/'hold-frames.jsonl').open() as stream:
        frames = [json.loads(line) for line in stream]
    if not data.get('skin_detector'):
        from piu_timeline.play.appearance import acquire
        with (directory/'frames.jsonl').open() as stream:
            acquire(data, directory, [json.loads(line) for line in stream])
    return reject_common_flashes(frames, observations(data, directory, frames))
