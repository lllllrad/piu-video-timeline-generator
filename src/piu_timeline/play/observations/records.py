"""Small retained frame contracts for consumers; image details stay with acquisition."""
import json

COUNTER_FIELDS = ('playback_seconds', 'source_pts_seconds', 'combo', 'combo_confidence')


def counter(frame):
    return {k: frame[k] for k in COUNTER_FIELDS if k in frame}


def positions(frame):
    return {**{k: frame[k] for k in ('playback_seconds', 'source_pts_seconds')},
            'notes': [{k: n[k] for k in ('lane', 'x', 'y')} for n in frame.get('notes', [])]}


def retained(data, path):
    """Use the validated channel projection, or stream legacy frame records."""
    channels = data.get('visual_channels', {})
    timeline = channels.get('timeline', {}).get('frames')
    popup = channels.get('popup', {}).get('observations')
    motion = channels.get('motion', {}).get('observations')
    if timeline is not None and popup is not None and motion is not None:
        if len(timeline) != len(popup) or len(timeline) != len(motion):
            raise ValueError('Retained channel frame counts differ')
        return [{'playback_seconds': time, 'source_pts_seconds': pts, 'combo': hud[0], 'combo_confidence': hud[1],
                 'notes': [{'lane': n[0], 'x': n[1], 'y': n[2]} for n in notes]}
                for (time, pts), hud, notes in zip(timeline, popup, motion, strict=True)]
    if not path.is_file():
        return []
    with path.open() as stream:
        return [{**counter(frame), **positions(frame)} for frame in (json.loads(line) for line in stream)]
