from copy import deepcopy
from contextlib import redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from piu_timeline.play_exclusions import exclusion_diagnostics


class ExclusionWarningTest(unittest.TestCase):
    def test_report_shows_warning_above_video_and_prints_final_report_path(self):
        from piu_timeline.play_report import write_report
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); data = self.sample()
            data.update(song='Example', chart='S20', media={'path':str(root/'source.mkv')})
            stderr = StringIO()
            with redirect_stderr(stderr):
                write_report(data, root/'report.html', root/'final')
            content = (root/'report.html').read_text()
            self.assertLess(content.index('id="exclusionWarnings"'), content.index('id="video"'))
            self.assertIn(str(root/'final/report.html'), stderr.getvalue())
            self.assertEqual(json.loads((root/'excluded-trajectories.json').read_text())['counts']['unaccounted_excluded_tracks'],1)

    def sample(self):
        return {'notes': [{'lane': 0, 'status': 'excluded', 'reason': 'receptor_not_observed_closely',
                           'target_seconds': None, 'points': [[10, 200], [10.1, 150]]}]}

    def test_visible_exclusion_is_warned_with_original_times_and_reason(self):
        native = self.sample(); before = deepcopy(native)
        result = exclusion_diagnostics(native, deepcopy(native))
        self.assertEqual(native, before)
        self.assertEqual(result['counts']['unaccounted_excluded_tracks'], 1)
        self.assertEqual(result['warnings'][0]['visible_start_seconds'], 10)
        self.assertEqual(result['warnings'][0]['reason'], 'receptor_not_observed_closely')

    def test_only_explicit_containing_chart_exception_suppresses_warning(self):
        native = self.sample(); projected = deepcopy(native)
        region = {'id':'gimmick','playback_start_seconds':9,'playback_end_seconds':11,
                  'processing':'standard','check_exceptions':[]}
        projected['chart_policy'] = {'regions':[region]}
        self.assertEqual(len(exclusion_diagnostics(native, projected)['warnings']), 1)
        region['check_exceptions'] = ['stage_grade_totals']
        self.assertEqual(len(exclusion_diagnostics(native, projected)['warnings']), 1)
        region['check_exceptions'] = ['timing_evidence']
        self.assertEqual(len(exclusion_diagnostics(native, projected)['chart_exceptions']), 1)
        region['playback_end_seconds'] = 10.05
        self.assertEqual(len(exclusion_diagnostics(native, projected)['warnings']), 1)

    def test_duplicate_owner_and_hold_components_remain_accounted(self):
        native = self.sample()
        native['notes'].extend([{'lane':0,'status':'estimated','target_seconds':10.2,'points':[[10,200]]},
                                {'lane':0,'status':'excluded','reason':'duplicate_head_component',
                                 'duplicate_of':1,'points':[[10,200]]}])
        projected = deepcopy(native)
        projected['notes'][1].update(status='excluded',reason='long_note_body_or_tail')
        result = exclusion_diagnostics(native, projected)
        self.assertEqual(len(result['warnings']), 1)
        self.assertEqual(len(result['accounted_observations']), 2)
