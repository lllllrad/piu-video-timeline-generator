"""Revision-checked interval truth. Analysis and native evidence are never changed."""
import fcntl
import json
import math
from pathlib import Path
from uuid import uuid4


class Conflict(ValueError):
    """Review revision or bound analysis no longer matches."""


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate(document, metadata, lanes):
    if document.get('schema') != 1 or document.get('status') not in ('draft', 'reviewed'):
        raise ValueError('Unsupported review schema or status')
    if document.get('analysis_fingerprint') != metadata['fingerprint']:
        raise Conflict('Analysis changed; review this interval against the new evidence')
    media = metadata['media']
    original=Path(media['path'])
    stat=original.stat()
    if (stat.st_size,str(stat.st_mtime_ns))!=(media['size_bytes'],media['mtime_ns']):
        raise Conflict('Original recording changed; restart with verified source evidence')
    from piu_timeline.review.index import signature
    if signature(Path(metadata['signature']['path']))!=metadata['signature']:
        raise Conflict('Prepared analysis changed; restart the editor before saving')
    if document.get('source') != {'id': metadata['source_id'], 'size_bytes': media['size_bytes'], 'mtime_ns': media['mtime_ns']}:
        raise Conflict('Review refers to different source media')
    pair = document.get('coverage')
    if not isinstance(pair, list) or len(pair) != 2 or not all(finite(v) for v in pair):
        raise ValueError('Review requires a finite coverage interval')
    a, b = pair
    if not metadata['start_seconds'] <= a < b <= metadata['end_seconds']:
        raise ValueError('Review interval must lie inside this play')
    if not isinstance(document.get('comment'), str) or len(document['comment']) > 20000:
        raise ValueError('Invalid review comment')
    ids = set()
    for kind in ('notes', 'ticks', 'scroll'):
        rows = document.get(kind)
        if not isinstance(rows, list) or len(rows) > 10000:
            raise ValueError('Invalid review collection')
        for row in rows:
            identity = row.get('id')
            if not isinstance(identity, str) or not 0 < len(identity) <= 200 or identity in ids:
                raise ValueError('Review object IDs must be unique')
            ids.add(identity)
            if not isinstance(row.get('evidence'), list) or any(not isinstance(v, str) or len(v) > 200 for v in row['evidence']):
                raise ValueError('Invalid evidence references')
            if kind != 'notes':
                t = row.get('seconds')
                if not finite(t) or not a <= t < b:
                    raise ValueError('Event lies outside coverage')
                weight = row.get('count') if kind == 'ticks' else row.get('multiplier')
                if kind == 'ticks':
                    if weight is not None and (type(weight) is not int or not 0 <= weight <= 9007199254740991):
                        raise ValueError('Tick weight must be a nonnegative integer or unknown')
                elif not finite(weight):
                    raise ValueError('Scroll multiplier must be finite')
                continue
            lane = row.get('lane')
            if type(lane) is not int or not 0 <= lane < lanes or row.get('kind') not in ('tap', 'hold', 'unknown'):
                raise ValueError('Invalid note lane or kind')
            start, end = row.get('start_seconds'), row.get('end_seconds')
            if start is not None and (not finite(start) or not a <= start < b):
                raise ValueError('Head lies outside coverage; mark censored heads unknown')
            if end is not None and (not finite(end) or not a <= end <= b):
                raise ValueError('Tail lies outside coverage; mark censored tails unknown')
            if start is not None and end is not None and start > end:
                raise ValueError('Tail precedes head')
            observed = row.get('observed_range')
            if not isinstance(observed, list) or len(observed) != 2 or not all(finite(v) for v in observed) or not a <= observed[0] <= observed[1] <= b:
                raise ValueError('Invalid observed interval')
            if row['kind'] == 'tap' and (start is None or end != start):
                raise ValueError('A tap requires one known time')


class ReviewStore:
    def __init__(self, root, metadata):
        self.root, self.metadata = root, metadata
        root.mkdir(parents=True, exist_ok=True)

    def list(self):
        rows = []
        for path in sorted(self.root.glob('*.json')):
            value = json.loads(path.read_text())
            rows.append({'id': path.stem, 'revision': value['revision'], 'coverage': value['coverage'],
                         'status': value['status'], 'stale': value['analysis_fingerprint'] != self.metadata['fingerprint']})
        return rows

    def path(self, identity):
        if not identity or any(c not in '0123456789abcdef-' for c in identity) or len(identity) > 40:
            raise ValueError('Invalid review ID')
        return self.root / f'{identity}.json'

    def get(self, identity):
        return json.loads(self.path(identity).read_text())

    def save(self, identity, document, base_revision):
        path = self.path(identity)
        if type(base_revision) is not int or base_revision < 0 or document.get('revision') != base_revision:
            raise ValueError('Invalid base revision')
        lanes = len(self.metadata['layout']['lanes'])
        validate(document, self.metadata, lanes)
        with (self.root / '.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            existing = self.get(identity) if path.exists() else None
            if base_revision != (existing['revision'] if existing else 0):
                raise Conflict('Review changed in another tab; reload before saving')
            result = {**document, 'revision': base_revision + 1}
            history=self.root/'history'/identity
            history.mkdir(parents=True,exist_ok=True)
            if existing is not None:
                version=history/f"{existing['revision']:06}.json"
                if not version.exists():
                    with version.open('x') as saved:
                        saved.write(json.dumps(existing,allow_nan=False,indent=2)+'\n')
            temporary = self.root / f'.{uuid4().hex}.tmp'
            try:
                temporary.write_text(json.dumps(result, allow_nan=False, indent=2) + '\n')
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        return result
