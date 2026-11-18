"""Performance changes preserve association inputs and diagnostic failure state."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from piu_timeline.play.effect_images import link_input
from piu_timeline.play.observations.performance import step


class PerformanceTests(unittest.TestCase):
    def test_compact_input_preserves_fallback_endpoints_and_unknown_holds(self):
        source = {'notes': [{'lane': 2, 'points': [[1, 3], [2, 4], [3, 5]],
                             'tracking_warnings': ['bulky evidence']}],
                  'hold_analysis': {'holds': [{'lane': 2, 'start_range': [1, 2], 'end_range': None,
                                               'body_frames': ['bulky evidence']}],
                                    'unresolved_tracks': [{'lane': 3, 'visible_start_seconds': 1}]}}
        result = link_input(source)
        self.assertEqual(result['notes'], [{'lane': 2, 'points': [[1, 3], [3, 5]]}])
        self.assertEqual(result['hold_analysis']['holds'], [{'lane': 2, 'start_range': [1, 2], 'end_range': None}])
        self.assertEqual(len(source['notes'][0]['points']), 3)

    def test_nested_timing_records_survive_failure(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with self.assertRaisesRegex(ValueError, 'measurement failed'):
                with step(directory, 'parent'):
                    with step(directory, 'child'):
                        raise ValueError('measurement failed')
            steps = json.loads((directory/'inspection-performance.json').read_text())['steps']
            for name in ('parent', 'child'):
                self.assertEqual(steps[name]['status'], 'failed')
                self.assertGreaterEqual(steps[name]['elapsed_seconds'], 0)
