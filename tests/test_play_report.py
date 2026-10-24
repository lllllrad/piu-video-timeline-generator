from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from piu_timeline.play_report import write_report
from piu_timeline.play_analysis import validate_layout, locate_layout, result_reference


class ReportTest(unittest.TestCase):
    def test_judgment_reference_requires_all_fields_and_one_selected_player(self):
        names = ('perfect', 'great', 'good', 'bad', 'miss')
        result = {name: value for name, value in zip(names, (1071, 22, 3, 1, 3))}
        result['fields'] = {name: {'status': 'recognized'} for name in names}
        segment = {'results': {'players': {'p2': result}}}
        self.assertEqual(result_reference(segment)['total'], 1100)
        segment['results']['players']['p1'] = result
        self.assertIsNone(result_reference(segment))
        self.assertEqual(result_reference(segment, 'p2')['total'], 1100)
        result['fields']['miss']['status'] = 'unknown'
        self.assertIsNone(result_reference(segment, 'p2'))

    def test_embedded_data_and_title_cannot_break_out_of_html(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'report.html'
            data = {'song': '</script><img src=x onerror=alert(1)>', 'chart': 'D22',
                    'media': {'path': str(Path(temporary) / 'source.mkv')}}
            write_report(data, path)
            text = path.read_text()
            self.assertNotIn('<img src=x', text)
            self.assertIn('\\u003c/script\\u003e', text)
            script = re.findall(r'<script>\s*(.*?)</script>', text, re.S)[0]
            if shutil.which('node'):
                js = Path(temporary) / 'report.js'
                js.write_text(script)
                subprocess.run(['node', '--check', str(js)], check=True, capture_output=True)

    def test_invalid_layout_fails_before_pixel_processing(self):
        with self.assertRaises(ValueError):
            validate_layout({'lanes': []})
        with self.assertRaises(ValueError):
            validate_layout({'lanes': [{'x': float('nan'), 'color': 'blue'}] * 5})
