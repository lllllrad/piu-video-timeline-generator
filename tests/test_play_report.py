from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import json
import numpy as np

from piu_timeline.play_report import write_report
from piu_timeline.play_analysis import validate_layout, locate_layout, result_reference, recover_layout


class ReportTest(unittest.TestCase):
    def test_shared_geometry_requires_current_spread_out_receptor_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);old=root/'segment-001';old.mkdir()
            pending=root/'segment-002.build-test';pending.mkdir()
            layout={'receptor_y':.14,'lanes':[{'x':.1+.08*i} for i in range(10)]}
            record={'path':'source.mkv'};roi=[0,0,100,100]
            (old/'analysis.json').write_text(json.dumps({'media':record,'game_roi':roi,'layout':layout}))
            points=[(100*layout['lanes'][i]['x'],14) for i in (0,3,6,9)]
            with patch('piu_timeline.play_analysis.receptor_centers',return_value=points), \
                    patch('piu_timeline.play_analysis.locate_layout',side_effect=ValueError('masked')), \
                    patch('piu_timeline.play_analysis.capture_game',side_effect=AssertionError('already verified')):
                result=recover_layout(record,roi,{'chart':'D20'},pending/'preview.png',
                                      np.zeros((100,100,3),dtype='uint8'),{'source_pts_seconds':100})
            self.assertEqual(result['method'],'corroborated_shared_geometry')
            self.assertEqual(result['lanes'],layout['lanes'])

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

    def report_runtime(self, notes, matches, miss_candidates=()):
        data = {'song': 'Song', 'chart': 'S20', 'media': {'path': '/tmp/source.mkv'},
                'start_seconds': 8, 'end_seconds': 20, 'notes': notes, 'matches': matches,
                'display_delay_correction_ms': 0, 'bootstrap': {'ocr_images': 0, 'missing_digits': []},
                'frame_count': 100, 'combo_readable_fraction': 1, 'combo_events': [],
                'judgment_events': [], 'excluded_notes': {}, 'limitations': [],
                'miss_candidates': miss_candidates,
                'layout': {'lanes': [{'name': 'C', 'color': 'yellow'}]}}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'report.html'
            write_report(data, path)
            result = subprocess.run(['node', str(Path(__file__).with_name('play_report_runtime.cjs')), str(path)],
                                    check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def test_comparison_includes_both_uncertainties_and_latency_correction(self):
        notes = [{'status': 'estimated', 'lane': 0, 'target_seconds': 10,
                  'prediction_uncertainty_seconds': .01},
                 {'status': 'estimated', 'lane': 0, 'target_seconds': 11,
                  'prediction_uncertainty_seconds': .02}]
        matches = [{'note': 0, 'target_seconds': 10, 'combo_event': None, 'judgment_event': 0,
                    'judgment_label': 'PERFECT', 'observation_lower_seconds': 10.02,
                    'observation_upper_seconds': 10.04, 'raw_offset_lower_ms': 20, 'raw_offset_upper_ms': 40}]
        result = self.report_runtime(notes, matches, [{'note': 1, 'judgment_event': 1}])
        self.assertEqual(result['targetRanges'], [[9.99, 10.01], [10.98, 11.02]])
        for actual, expected in zip(result['initialDifferences'][0], (10, 50)):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(result['correctedDifferences'][0], (-20, 20)):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(result['correctedInputs'][0], (9.99, 10.01)):
            self.assertAlmostEqual(actual, expected)
        self.assertIn('Later than target range', result['initialRows'][0][3])
        self.assertIn('Overlaps target range', result['correctedRows'][0][3])
        self.assertIsNone(result['initialInputs'][1])
        self.assertIsNone(result['correctedDifferences'][1])
        self.assertEqual(result['correctedRows'][1][2], 'Unconfirmed')
        self.assertIn('Possible MISS', result['correctedRows'][1][4])
        self.assertIn('Input: Unconfirmed', result['details'][1][0])
        self.assertEqual(result['correctedRows'][0][1], result['initialRows'][0][1])

    def test_shared_aggregate_bracket_is_preserved_and_missing_motion_excluded(self):
        notes = [{'status': 'estimated', 'lane': 0, 'target_seconds': target,
                  'prediction_uncertainty_seconds': .01} for target in (10, 10.03)]
        notes.append({'status': 'excluded', 'lane': 0, 'target_seconds': None, 'points': [[12, .3]]})
        matches = [{'note': i, 'target_seconds': note['target_seconds'], 'combo_event': None,
                    'judgment_event': 0, 'aggregate_row_count': 2, 'observation_lower_seconds': 9.98,
                    'observation_upper_seconds': 10.04, 'raw_offset_lower_ms': -20, 'raw_offset_upper_ms': 40}
                   for i, note in enumerate(notes[:2])]
        result = self.report_runtime(notes, matches)
        self.assertEqual(len(result['initialRows']), 2)
        self.assertEqual(result['initialInputs'], [[9.98, 10.04]] * 2)
        self.assertTrue(all('aggregate row bracket' in row[4] for row in result['initialRows']))
        self.assertIn('Aggregate refresh bracket', result['details'][0][2])

    def test_comparison_legacy_combo_bracket_early_input_and_no_matches(self):
        note = {'status': 'estimated', 'lane': 0, 'target_seconds': 10,
                'prediction_uncertainty_seconds': .01}
        match = {'note': 0, 'target_seconds': 10, 'combo_event': None,
                 'combo_lower_seconds': 9.95, 'combo_upper_seconds': 9.97,
                 'raw_offset_lower_ms': -50, 'raw_offset_upper_ms': -30}
        result = self.report_runtime([note], [match])
        self.assertIn('Earlier than target range', result['initialRows'][0][3])
        self.assertEqual(result['initialInputs'], [[9.95, 9.97]])
        match['judgment_label'] = 'MISS'
        result = self.report_runtime([note], [match])
        self.assertIsNone(result['initialInputs'][0])
        result = self.report_runtime([note], [])
        self.assertEqual(result['initialInputs'], [None])
        self.assertIn('No matched input evidence', result['initialRows'][0][4])
        self.assertEqual(self.report_runtime([], [])['initialRows'], [])
