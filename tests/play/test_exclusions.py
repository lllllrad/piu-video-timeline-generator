from copy import deepcopy
from contextlib import redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from piu_timeline.play.exclusions import exclusion_diagnostics, recognition_diagnostics


class ExclusionWarningTest(unittest.TestCase):
    def test_inspector_retains_warning_tab_artifact_and_final_output_path(self):
        from piu_timeline.play.presentation import build_report as write_report
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); data = self.sample()
            data.update(song='Example', chart='S20', media={'path':str(root/'source.mkv')})
            stderr = StringIO()
            with redirect_stderr(stderr):
                write_report(data, root/'report.html', root/'final')
            content = (root/'report.html').read_text()
            self.assertIn('id="tab-warnings"', content)
            self.assertIn('id="warningRows"', content)
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
        for note in native['notes'][1:]:
            note['points'] = [[10+i*.02, 200-i*5] for i in range(4)]
        projected = deepcopy(native)
        projected['notes'][1].update(status='excluded',reason='long_note_body_or_tail')
        unverified = exclusion_diagnostics(native, projected)
        self.assertEqual(len(unverified['warnings']), 3)
        projected['hold_analysis'] = {'holds': [{'covered_notes': [1], 'component_evidence': {
            '1': {'kind': 'registered_cap', 'source_pts_seconds': [10, 10.02, 10.04, 10.06]}}}]}
        result = exclusion_diagnostics(native, projected)
        self.assertEqual(len(result['warnings']), 1)
        self.assertEqual(len(result['accounted_observations']), 2)

    def test_unknown_hold_ends_and_ambiguous_input_remain_explicit_warnings(self):
        data = {'notes': [{'lane': 0}], 'hold_analysis': {'holds': [{
            'id': 0, 'lane': 0, 'start_range': [10, 10.02], 'end_range': None,
            'start_censored': False, 'end_censored': True, 'last_body_seconds': 11}]}}
        ranges = {'notes': {0: {'status': 'possible', 'target_range': [10, 10.02]}}}
        result = recognition_diagnostics(data, ranges)
        self.assertEqual({r['reason'] for r in result['warnings']},
                         {'hold_end_unresolved', 'timing_evidence_unresolved'})
        region = {'id': 'annotation', 'processing': 'standard', 'check_exceptions': [],
                  'playback_start_seconds': 9, 'playback_end_seconds': 12}
        data['chart_policy'] = {'regions': [region]}
        self.assertEqual(len(recognition_diagnostics(data, ranges)['warnings']), 2)
        region['check_exceptions'] = ['timing_evidence']
        result = recognition_diagnostics(data, ranges)
        self.assertEqual(result['warnings'], [])
        self.assertEqual(len(result['chart_exceptions']), 2)

    def test_unknown_active_effect_reaches_warning_queue_despite_timing_exception(self):
        from piu_timeline.play.gimmicks import apply_gimmicks
        effect={'id':'art','kind':'unimplemented_art','review_status':'pending',
                'playback_start_seconds':10.,'playback_end_seconds':12.}
        region={'id':'timing','playback_start_seconds':9.,'playback_end_seconds':13.,
                'processing':'exclude_timing','check_exceptions':['timing_evidence']}
        data={'notes':[],'chart_policy':{'gimmick_candidates':[effect],'regions':[region]}}
        original=deepcopy(data)
        result=recognition_diagnostics(apply_gimmicks(data),{'notes':{}})
        self.assertEqual(data,original)
        self.assertEqual(result['counts'],{'chart_effect_handler_missing':1})
        warning=result['warnings'][0]
        self.assertEqual((warning['gimmick_candidate'],warning['effect_kind']),('art','unimplemented_art'))
        self.assertEqual((warning['visible_start_seconds'],warning['visible_end_seconds']),(10.,12.))
        self.assertEqual(result['chart_exceptions'],[])
        effect['review_status']='confirmed'
        self.assertEqual(len(recognition_diagnostics(apply_gimmicks(data),{'notes':{}})['warnings']),1)
        effect['review_status']='rejected'
        self.assertEqual(recognition_diagnostics(apply_gimmicks(data),{'notes':{}})['warnings'],[])

    def test_persistent_pixel_gap_accounts_for_a_false_hold_candidate_only_when_both_caps_remain(self):
        connection={'decision':'disconnected_caps','head_note':0,'tail_note':1,
                    'visible_start_seconds':10.,'visible_end_seconds':10.2,
                    'gap_source_pts_seconds':[10+i/60 for i in range(10)],
                    'connected_source_pts_seconds':[10.18,10.2]}
        record={'lane':0,'reason':'unresolved_hold_geometry','visible_start_seconds':10.,
                'visible_end_seconds':10.2,'cap_continuity':connection}
        data={'notes':[{'status':'estimated','lane':0} for _ in range(2)],
              'hold_analysis':{'holds':[],'unresolved_tracks':[record]}}
        result=recognition_diagnostics(data,{'notes':{}})
        self.assertFalse(result['warnings'])
        self.assertEqual(result['accounted_hold_fragments'][0]['interpretation'],'separate_caps_with_observed_gap')
        data['notes'][1]['status']='excluded'
        self.assertEqual(len(recognition_diagnostics(data,{'notes':{}})['warnings']),1)
        data['notes'][1]['status']='estimated'
        connection['gap_source_pts_seconds']=connection['gap_source_pts_seconds'][:7]
        self.assertEqual(len(recognition_diagnostics(data,{'notes':{}})['warnings']),1)
