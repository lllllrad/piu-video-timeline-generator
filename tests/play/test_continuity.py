"""All unexplained native gaps and observed motion changes stay reviewable."""
from copy import deepcopy
import unittest

from piu_timeline.play.continuity import continuity_diagnostics
from piu_timeline.play.motion_warnings import motion_warnings
from piu_timeline.play.exclusions import recognition_diagnostics


def fixture(ys=None):
    times=[i/60 for i in range(31)]
    ys=ys if ys is not None else [300-300*t for t in times]
    frames=[{'playback_seconds':t,'source_pts_seconds':10+t,
             'notes':[{'lane':0,'x':.2,'y':y/365}]} for t,y in zip(times,ys)]
    data={'analysis_width':650,'analysis_height':365,
          'layout':{'lanes':[{'x':x} for x in (.2,.26,.32,.38,.44)],
                    'receptor_y':.142,'note_y_max':.95,'combo_roi':[.43,.52,.14,.075]},
          'notes':[{'lane':0,'status':'estimated','points':[[t,y] for t,y in zip(times,ys)],
                    'target_seconds':.8,'prediction_uncertainty_seconds':.01}],
          'matches':[{'note':0,'judgment_label':'PERFECT'}]}
    return data,frames


class ContinuityTest(unittest.TestCase):
    def test_single_missing_frame_warns_even_if_head_reappears_and_timing_is_matched(self):
        data,frames=fixture();del data['notes'][0]['points'][10];frames[10]['notes']=[]
        native=deepcopy(data);result=continuity_diagnostics(data,frames)
        self.assertEqual(data,native)
        gaps=[w for w in result['warnings'] if w['reason']=='unexplained_head_detection_gap']
        self.assertEqual(len(gaps),1)
        self.assertEqual(gaps[0]['missing_frames'],1)
        self.assertEqual(gaps[0]['source_pts_seconds'],[10+10/60]*2)

    def test_premature_terminal_loss_warns_without_minimum_track_length(self):
        data,frames=fixture();data['notes'][0]['points']=data['notes'][0]['points'][:1]
        for frame in frames[1:]:frame['notes']=[]
        result=continuity_diagnostics(data,frames)
        self.assertEqual(result['warnings'][0]['reason'],'unexplained_head_disappearance')
        self.assertEqual(result['warnings'][0]['observed_points'],1)

    def test_named_hud_overlap_is_accounted_but_same_height_in_another_lane_is_not(self):
        for covered in (False,True):
            data,frames=fixture([200-300*t for t in [i/60 for i in range(31)]])
            data['layout']['combo_roi']=[.15 if covered else .43,.52,.14,.075]
            del data['notes'][0]['points'][2];frames[2]['notes']=[]
            result=continuity_diagnostics(data,frames)
            gaps=[r for r in result['warnings'] if r['reason']=='unexplained_head_detection_gap']
            self.assertEqual(bool(gaps),not covered)
            if covered:self.assertTrue(result['known_occlusions'][0]['regions'])

    def test_known_hud_does_not_excuse_missing_head_after_predicted_exit(self):
        data,frames=fixture([260-350*t for t in [i/60 for i in range(31)]])
        data['layout']['combo_roi']=[.15,.52,.14,.075]
        data['notes'][0]['points']=data['notes'][0]['points'][:10]
        for frame in frames[10:]:frame['notes']=[]
        result=continuity_diagnostics(data,frames)
        self.assertTrue(result['known_occlusions'])
        self.assertTrue(any(r['reason']=='unexplained_head_disappearance' for r in result['warnings']))

    def test_explicit_judgment_overlap_is_recorded_without_a_missing_frame_warning(self):
        data,frames=fixture([200-300*t for t in [i/60 for i in range(31)]])
        data['layout']['judgment_roi']=[.15,.35,.12,.15]
        del data['notes'][0]['points'][10];frames[10]['notes']=[]
        result=continuity_diagnostics(data,frames)
        self.assertEqual(result['warnings'],[])
        self.assertIn('judgment_word',result['known_occlusions'][0]['regions'])

    def test_receptor_boundary_and_end_of_capture_are_accounted_without_claiming_input(self):
        for clipped in (False,True):
            data,frames=fixture([150-300*t for t in [i/60 for i in range(31)]])
            if not clipped:
                data['notes'][0]['points']=data['notes'][0]['points'][:15]
                for frame in frames[15:]:frame['notes']=[]
            result=continuity_diagnostics(data,frames)
            self.assertEqual(result['warnings'],[])
            if not clipped:self.assertTrue(result['accounted_exits'])

    def test_applied_visibility_effect_accounts_only_for_its_observed_loss_and_not_earlier_failure(self):
        data,frames=fixture()
        data['notes'][0]['points']=data['notes'][0]['points'][:8]
        for frame in frames[8:]:frame['notes']=[]
        data['visual_channels']={'processing':{'notes':[{'note':0,'status':'visibility_modified',
             'gimmick_candidates':['hidden'],'visibility_loss':{'range':[.3,.32]}}]}}
        result=continuity_diagnostics(data,frames)
        self.assertTrue(result['warnings'])
        self.assertTrue(all(r['visible_end_seconds']<.3 for r in result['warnings']))
        self.assertTrue(any(r['reason']=='chart_visibility_modifier' for r in result['known_occlusions']))

    def test_generic_timing_exclusion_cannot_hide_visibility_or_motion_warnings(self):
        data,frames=fixture();del data['notes'][0]['points'][10];frames[10]['notes']=[]
        data['visibility_diagnostics']=continuity_diagnostics(data,frames)
        region={'id':'timing','processing':'exclude_timing','check_exceptions':['timing_evidence'],
                'playback_start_seconds':0,'playback_end_seconds':2}
        data['chart_policy']={'regions':[region]}
        self.assertTrue(recognition_diagnostics(data,{'notes':{}})['warnings'])
        region['check_exceptions'].append('note_visibility')
        self.assertFalse(recognition_diagnostics(data,{'notes':{}})['warnings'])


class MotionWarningTest(unittest.TestCase):
    def test_successfully_fitted_stop_and_acceleration_still_warn(self):
        data,frames=fixture([300]*9+[300-10*(i-8) for i in range(9,31)])
        warnings=motion_warnings(data,frames)
        self.assertTrue(any(r['reason']=='possible_scroll_stop_or_capture_freeze' for r in warnings))
        data,frames=fixture([300-200*t if t<.25 else 250-600*(t-.25) for t in [i/60 for i in range(31)]])
        warnings=motion_warnings(data,frames)
        self.assertTrue(any(r['reason']=='scroll_speed_change' for r in warnings))
        self.assertTrue(all(r['check']=='scroll_motion' for r in warnings))

    def test_source_timestamp_translation_preserves_motion_warnings(self):
        data,frames=fixture([300]*9+[300-10*(i-8) for i in range(9,31)])
        expected=[r['reason'] for r in motion_warnings(data,frames)]
        data['notes'][0]['points']=[[t+4000,y] for t,y in data['notes'][0]['points']]
        for frame in frames:
            frame['playback_seconds']+=4000;frame['source_pts_seconds']+=4000
        self.assertEqual([r['reason'] for r in motion_warnings(data,frames)],expected)

    def test_constant_speed_and_normal_duplicated_render_frames_are_not_stops(self):
        for duplicate in (False,True):
            ys=[300-10*(i//2) if duplicate else 300-5*i for i in range(31)]
            data,frames=fixture(ys)
            self.assertEqual(motion_warnings(data,frames),[])
