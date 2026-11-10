"""Independent interval truth, compact transport and source-integrity regressions."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from piu_timeline.review.index import build, ReportIndex
from piu_timeline.review.server import bounded_detail
from piu_timeline.review.store import Conflict, ReviewStore


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.prepared = self.root / 'report-data.json'
        self.media = self.root / 'recording.mp4'
        self.media.write_bytes(b'original source')
        stat = self.media.stat()
        self.data = {'media': {'path': str(self.media), 'size_bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns},
                     'start_seconds': 10, 'end_seconds': 30, 'segment_number': 1,
                     'layout': {'lanes': [{}] * 5},
                     'notes': [{'lane': 0, 'points': [[11, 100], [12, 20]], 'target_seconds': 12,
                                'proof': {'opaque': 9223372036854775807}}],
                     'frame_timeline': [{'time': 11, 'source_pts': 1001}],
                     'hold_analysis': {'holds': [{'lane': 2, 'start_range': [14, 14.1], 'end_range': [16, 16.1]}]},
                     'visual_channels': {'timeline': {'frames': [[11, 1001]]},
                                         'popup': {'observations': [[None, .2]]},
                                         'motion': {'observations': [[[0, .1, .2, .9]]]}},
                     'recognition_diagnostics': {'warnings': [{'reason': 'hidden', 'visible_start_seconds': 13, 'visible_end_seconds': 14}]}}
        self.prepared.write_text(json.dumps(self.data))
        self.index = ReportIndex(build(self.prepared, self.root / 'index.sqlite'))
        self.meta = {**self.index.metadata(), 'source_id': 'synthetic'}
        self.store = ReviewStore(self.root / 'intervals', self.meta)

    def document(self):
        return {'schema': 1, 'revision': 0, 'source': {'id': 'synthetic', 'size_bytes': self.meta['media']['size_bytes'],
                                                     'mtime_ns': self.meta['media']['mtime_ns']},
                'analysis_fingerprint': self.meta['fingerprint'], 'coverage': [11, 17], 'status': 'draft',
                'notes': [{'id': 'hold', 'lane': 0, 'kind': 'hold', 'start_seconds': None, 'end_seconds': 15,
                           'observed_range': [11, 15], 'evidence': []}],
                'ticks': [{'id': 'tick-a', 'seconds': 12.13, 'count': 3, 'evidence': []},
                          {'id': 'tick-b', 'seconds': 12.71, 'count': None, 'evidence': []}],
                'scroll': [{'id': 'speed', 'seconds': 13, 'multiplier': .5, 'evidence': []}], 'comment': ''}

    def test_streamed_index_retains_source_identity_channels_and_untimed_evidence(self):
        before = self.prepared.stat().st_mtime_ns
        self.assertEqual(self.meta['media']['mtime_ns'], str(self.media.stat().st_mtime_ns))
        self.assertEqual(self.index.window('notes', 11, 13)['total'], 1)
        self.assertEqual(self.index.window('holds', 15, 16)['total'], 1)
        self.assertEqual(self.index.window('warnings', 13, 14)['total'], 1)
        self.assertEqual(self.index.detail('notes:0')['proof']['opaque'], 9223372036854775807)
        popup = self.index.window('popup', 10, 12)['rows'][0]
        self.assertEqual((popup['time'], popup['source_pts']), (11, 1001))
        self.assertEqual(self.index.detail('motion:0')['values'], [[0, .1, .2, .9]])
        path = build(self.prepared, self.root / 'index.sqlite')
        self.assertEqual(path, self.index.path)
        self.assertEqual(self.prepared.stat().st_mtime_ns, before)
        self.assertEqual(self.media.read_bytes(), b'original source')

    def test_censored_interval_weighted_ticks_and_revision_conflicts(self):
        document = self.document()
        saved = self.store.save('abcdef', document, 0)
        self.assertEqual(saved['ticks'], document['ticks'])
        self.assertIsNone(saved['notes'][0]['start_seconds'])
        with self.assertRaises(Conflict):
            self.store.save('abcdef', document, 0)
        changed = deepcopy(saved)
        changed['status'] = 'reviewed'
        second = self.store.save('abcdef', changed, 1)
        self.assertEqual(second['revision'], 2)
        self.assertEqual(self.prepared.read_text(), json.dumps(self.data))

    def test_unknown_is_not_zero_and_outside_coverage_is_rejected(self):
        document = self.document()
        document['ticks'][0]['seconds'] = 18
        with self.assertRaises(ValueError):
            self.store.save('abc', document, 0)
        document = self.document()
        document['notes'][0]['start_seconds'] = 10
        with self.assertRaises(ValueError):
            self.store.save('abc', document, 0)
        document = self.document()
        document['analysis_fingerprint'] = 'foreign'
        with self.assertRaises(Conflict):
            self.store.save('abc', document, 0)
        with self.assertRaises(ValueError):
            self.store.get('../escape')

    def test_large_evidence_preview_and_queries_are_bounded(self):
        value = bounded_detail({'points': [[i, 20] for i in range(2000)]})
        self.assertEqual(value['points']['total'], 2000)
        self.assertEqual(len(value['points']['items']), 30)
        with self.assertRaises(ValueError):
            self.index.window('notes', 0, 20, limit=501)
        with sqlite3.connect(self.index.path) as db:
            self.assertEqual(db.execute('select count(*) from rows').fetchone()[0], 7)

    def test_http_range_frame_binding_and_conflicting_writes(self):
        from http.server import ThreadingHTTPServer
        from threading import Thread
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        from piu_timeline.review.server import handler_for
        assets = self.root / 'app'
        assets.mkdir()
        (assets / 'index.html').write_text('small shell')
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.index, self.store, assets, self.root))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base + '/api/meta') as response:
                meta = json.load(response)
            with urlopen(Request(base + '/media', headers={'Range': 'bytes=2-5'})) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), b'igin')
            with urlopen(base + '/api/frame?time=11') as response:
                self.assertEqual(json.load(response)['source_pts'], 1001)
            data = json.dumps({'base_revision': 0, 'document': self.document()}).encode()
            request = Request(base + '/api/review?id=abc', data=data, method='PUT', headers={'X-Review-Token': meta['write_token']})
            with urlopen(request) as response:
                self.assertEqual(json.load(response)['revision'], 1)
            with self.assertRaises(HTTPError) as conflict:
                urlopen(request)
            self.assertEqual(conflict.exception.code, 409)
            with self.assertRaises(HTTPError) as rejected:
                urlopen(Request(base + '/api/meta', headers={'Host': 'foreign.example'}))
            self.assertEqual(rejected.exception.code, 403)
            with self.assertRaises(HTTPError) as outside:
                urlopen(base + '/api/window?kind=notes&start=0&end=1000')
            self.assertEqual(outside.exception.code, 400)
            self.assertEqual(self.media.read_bytes(), b'original source')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_default_report_reuses_prepared_data_and_never_embeds_native_payload(self):
        from piu_timeline.play.report import write_report
        prepared = self.root / 'report-data.json'
        content = prepared.read_bytes()
        # A prepared file already exists; rendering must not serialize the composed view again.
        data = {'media': {'path': str(self.media)}, 'song': '</script><img src=x>', 'chart': 'S10',
                'native_proof': object(), 'coverage': {}}
        write_report(data, self.root / 'report.html',prepared_path=prepared)
        html = (self.root / 'report.html').read_text()
        self.assertLess(len(html), 10000)
        self.assertNotIn('<img src=x>', html)
        self.assertNotIn('native_proof', html)
        self.assertIn('Open local Play review', html)
        self.assertEqual(prepared.read_bytes(), content)

    def test_direct_render_replaces_stale_prepared_data_explicitly(self):
        from piu_timeline.play.report import write_report
        data={'media':{'path':str(self.media)},'song':'Updated','chart':'S10','notes':[{'lane':4}]}
        write_report(data,self.root/'report.html')
        self.assertEqual(json.loads(self.prepared.read_text()),data)
