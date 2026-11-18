from pathlib import Path
import tempfile
import unittest
import json

from piu_timeline.play.presentation import prepare_report
from piu_timeline.play.report import write_report as render_report


def write_report(data,path,final_directory=None):
    return render_report(prepare_report(data,path,final_directory),path,final_directory)


class ReportTest(unittest.TestCase):
    def test_registration_refresh_updates_saved_view_without_rerunning_consumers(self):
        from unittest.mock import patch
        from piu_timeline.play.presentation import refresh_registration
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = {'song':'Example', 'chart':'D20', 'media':{'path':str(root/'source.mkv')}}
            write_report(data, root/'report.html')
            record = {'status':'pending', 'reason':'Independent native anchors unavailable'}
            (root/'chart-registration.json').write_text(json.dumps(record))
            with patch('piu_timeline.play.observations.presentation.prepare', side_effect=AssertionError('must not analyze')):
                refresh_registration(data, root)
            saved = json.loads((root/'report-data.json').read_text())
            self.assertEqual(saved['inspector_artifacts']['chart']['registration'],record)
            self.assertNotIn(record['reason'],(root/'report.html').read_text())
            self.assertLess((root/'report.html').stat().st_size,10000)


    def test_saved_ucs_note_links_reject_changed_source_order_media_and_edited_chart(self):
        from hashlib import sha256
        from piu_timeline.play.observations.inspector import snapshot
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = {'media': {'size_bytes': 100, 'mtime_ns': 1234567890123456789},
                    'segment_number': 1, 'notes': [{'lane': 0}, {'lane': 1}]}
            text = ':Format=1\nX.\n'
            chart = root/'chart.ucs'
            chart.write_text(text)
            (root/'chart-registration.json').write_text(json.dumps({'status':'existing', 'chart':str(chart)}))
            metadata = {'source': {'segment_number':1, 'media_size_bytes':100,
                        'media_mtime_ns':data['media']['mtime_ns'],
                        'analysis_sha256':sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()},
                        'generated_ucs_sha256':sha256(text.encode()).hexdigest(), 'placements':[{'note':0}]}
            (root/'metadata.json').write_text(json.dumps(metadata))
            self.assertTrue(snapshot(data,root)['chart']['linked'])
            self.assertFalse(snapshot({**data,'notes':list(reversed(data['notes']))},root)['chart']['linked'])
            self.assertFalse(snapshot({**data,'media':{'size_bytes':101,'mtime_ns':data['media']['mtime_ns']}},root)['chart']['linked'])
            chart.write_text(':Format=1\n.X\n')
            edited = snapshot(data,root)['chart']
            self.assertFalse(edited['linked'])
            self.assertEqual(edited['metadata']['placements'],[{'note':0}])
            chart.unlink()
            self.assertIn('unavailable',snapshot(data,root)['chart']['error'])


    def test_title_and_media_paths_are_escaped(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'report.html'
            write_report({'song': '</title><img>', 'chart': 'D22',
                          'media': {'path': str(path.with_name('source file.mkv'))}}, path)
            html = path.read_text()
            self.assertNotIn('<img>', html)
            self.assertIn('&lt;/title&gt;&lt;img&gt;', html)
            self.assertIn('source%20file.mkv', html)
