"""Stream prepared reports into a disposable SQLite query index, never into HTML."""
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
import zlib

import ijson

FORMAT = 4
COLLECTIONS = {
    'notes.item': 'notes', 'matches.item': 'matches',
    'hold_analysis.holds.item': 'holds',
    'hold_analysis.observed_holds.item': 'observed_holds',
    'recognition_diagnostics.warnings.item': 'warnings',
    'exclusion_diagnostics.warnings.item': 'exclusions',
    'frame_timeline.item': 'frames',
    'combo_events.item': 'combo', 'judgment_events.item': 'judgments',
    'visual_channels.timeline.frames.item': 'channel_frames',
    'visual_channels.popup.observations.item': 'popup',
    'visual_channels.receptors.observations.item': 'receptors',
    'visual_channels.motion.observations.item': 'motion',
    'visual_channels.processing.notes.item': 'processing',
}
META = {'media', 'song', 'chart', 'start_seconds', 'end_seconds', 'layout',
        'coverage', 'game_roi', 'analysis_width', 'analysis_height', 'segment_number'}


def signature(path):
    stat = path.stat()
    return {'path': str(path.resolve()), 'size': stat.st_size, 'mtime_ns': str(stat.st_mtime_ns), 'format': FORMAT}


def bounds(value):
    """Do not turn unresolved targets into chart times; bounds only index evidence."""
    values = []
    for key in ('target_seconds', 'playback_seconds', 'time', 'seconds', 'start_seconds',
                'end_seconds', 'visible_start_seconds', 'visible_end_seconds',
                'first_seconds', 'last_seconds', 'last_body_seconds'):
        item = value.get(key)
        if isinstance(item, (float, int)) and not isinstance(item, bool):
            values.append(float(item))
    for key in ('points', 'observations', 'samples', 'image_connection_evidence'):
        points = value.get(key, [])
        if isinstance(points,list) and points:
            for point in (points[0], points[-1]):
                t = point[0] if isinstance(point, list) else point.get('time', point.get('playback_seconds'))
                if isinstance(t, (float, int)):
                    values.append(float(t))
    for key in ('target_range', 'time_range', 'crossing_capture_range', 'interval', 'visible_range_seconds', 'start_range', 'end_range'):
        pair = value.get(key)
        if isinstance(pair, list) and len(pair) == 2:
            values.extend(float(v) for v in pair if isinstance(v, (int, float)))
    return (min(values), max(values)) if values else (None, None)


def compact(value, collection, identity):
    keep = ('lane', 'status', 'reason', 'check', 'target_seconds', 'start_seconds',
            'end_seconds', 'visible_start_seconds', 'visible_end_seconds',
            'source_pts', 'source_pts_seconds', 'time', 'playback_seconds',
            'note', 'judgment_label', 'kind', 'type', 'fit_method', 'count', 'note_type', 'observed_note_type', 'type_status', 'start_range', 'end_range')
    row = {k: value[k] for k in keep if k in value}
    row.update(id=f'{collection}:{identity}', collection=collection)
    low, high = bounds(value)
    row.update(observed_range=[low, high])
    return row


def records(path):
    """One parser pass; materialize only one selected record at a time."""
    builder = None
    active = None
    depth = 0
    with path.open('rb') as source:
        for prefix, event, value in ijson.parse(source, use_float=True):
            if builder is not None:
                builder.event(event, value)
                if event in ('start_map', 'start_array'):
                    depth += 1
                elif event in ('end_map', 'end_array'):
                    depth -= 1
                if depth == 0:
                    yield active, builder.value
                    builder = active = None
                continue
            if prefix in META or prefix in COLLECTIONS:
                active = prefix
                if event in ('start_map', 'start_array'):
                    builder = ijson.ObjectBuilder()
                    builder.event(event, value)
                    depth = 1
                elif event not in ('map_key', 'end_map', 'end_array'):
                    yield active, value


def build(prepared, destination):
    prepared, destination = Path(prepared), Path(destination)
    expected = signature(prepared)
    if destination.is_file():
        with sqlite3.connect(destination) as db:
            try:
                if json.loads(db.execute("select value from meta where key='signature'").fetchone()[0]) == expected:
                    return destination
            except (sqlite3.DatabaseError, TypeError):
                pass
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = destination.with_name(f'.index-{uuid4().hex}.sqlite')
    try:
        with sqlite3.connect(pending) as db:
            db.executescript('create table meta(key text primary key,value text); '
                             'create table rows(id text primary key,kind text,lo real,hi real,summary text,detail blob);')
            counts = {}
            for prefix, value in records(prepared):
                if prefix in META:
                    # Opaque source integers are serialized as strings before browser transport.
                    if prefix == 'media':
                        value['mtime_ns'] = str(value['mtime_ns'])
                    db.execute('insert into meta values(?,?)', (prefix, json.dumps(value)))
                else:
                    kind = COLLECTIONS[prefix]
                    identity = counts.get(kind, 0)
                    if kind=='channel_frames':
                        if not isinstance(value,list) or len(value)!=2:
                            raise ValueError('Invalid channel timeline')
                        value={'time':value[0],'source_pts':value[1]}
                    elif kind in ('popup','receptors','motion'):
                        saved=db.execute('select summary from rows where id=?',(f'channel_frames:{identity}',)).fetchone()
                        if saved is None:raise ValueError('Channel observation lacks its original source timeline')
                        frame=json.loads(saved[0])
                        value={'time':frame['time'],'source_pts':frame['source_pts'],'values':value}
                    counts[kind] = identity + 1
                    summary = compact(value, kind, identity)
                    lo, hi = summary['observed_range']
                    db.execute('insert into rows values(?,?,?,?,?,?)',
                               (summary['id'], kind, lo, hi, json.dumps(summary),
                                zlib.compress(json.dumps(value).encode(), 1)))
            if signature(prepared) != expected:
                raise ValueError('Prepared analysis changed while indexing; retry after publication')
            db.executescript('create index by_interval on rows(kind,lo,hi);')
            with prepared.open('rb') as content:
                content_hash=hashlib.file_digest(content,'sha256').hexdigest()
            if signature(prepared)!=expected:
                raise ValueError('Prepared analysis changed while fingerprinting')
            fingerprint=hashlib.sha256(f'{FORMAT}:{content_hash}'.encode()).hexdigest()
            for key, value in [('signature', expected), ('fingerprint', fingerprint), ('counts', counts), ('prepared_sha256',content_hash)]:
                db.execute('insert into meta values(?,?)', (key, json.dumps(value)))
        pending.replace(destination)
    finally:
        pending.unlink(missing_ok=True)
    return destination


class ReportIndex:
    def __init__(self, path):
        self.path = path

    def metadata(self):
        with sqlite3.connect(self.path) as db:
            return {key: json.loads(value) for key, value in db.execute('select key,value from meta')}

    def window(self, kind, start, end, offset=0, limit=200):
        if kind not in COLLECTIONS.values() or not 0 < limit <= 500 or offset < 0:
            raise ValueError('Invalid collection or page')
        with sqlite3.connect(self.path) as db:
            predicate = 'kind=? and lo<=? and hi>=?'
            args = (kind, end, start)
            total = db.execute(f'select count(*) from rows where {predicate}', args).fetchone()[0]
            rows = db.execute(f'select summary from rows where {predicate} order by lo,id limit ? offset ?', (*args, limit, offset))
            return {'rows': [json.loads(row[0]) for row in rows], 'total': total,
                    'next_offset': offset + limit if offset + limit < total else None}

    def detail(self, identity):
        with sqlite3.connect(self.path) as db:
            row = db.execute('select detail from rows where id=?', (identity,)).fetchone()
        if row is None:
            raise KeyError(identity)
        return json.loads(zlib.decompress(row[0]))

    def frame_at(self, seconds):
        with sqlite3.connect(self.path) as db:
            row=db.execute("select id from rows where kind='channel_frames' and lo between ? and ? order by abs(lo-?) limit 1",(seconds-.1,seconds+.1,seconds)).fetchone()
            if row is None:return None
            number=row[0].split(':')[1]
            result=self.detail(row[0])
            for kind in ('motion','popup','receptors'):
                try:result[kind]=self.detail(f'{kind}:{number}')['values']
                except KeyError:result[kind]=None
            # Bound native scene density without inventing observations.
            if isinstance(result.get('motion'),list):
                result['motion_total']=len(result['motion'])
                result['motion']=result['motion'][:500]
            return result
