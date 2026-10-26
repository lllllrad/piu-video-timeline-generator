"""Independent native clocks, measured ratios and explicit estimation limits."""
import unittest
import math
from copy import deepcopy

from piu_timeline.play.speed_estimation import estimate
from piu_timeline.play.registered_coordinates import FORMAT as COORDINATE_FORMAT


def scenario(ratio=2.,repeated=False):
    samples=[]
    for i in range(300):
        time=i/60;render=(i//2)*2/60 if repeated else time
        phase=240*min(render,2)+240*ratio*max(0,render-2)
        samples.append({'time':1000+time,'source_pts':9000+time,'phase':phase,'chunk':0,'support':4,'lanes':2})
    return {'analysis_width':400,'layout':{'lanes':[{'x':.2},{'x':.3}]},
            'scroll_motion':{'format':{'method':'registered_peer_displacement'},
                             'coordinate_registration':{'format':COORDINATE_FORMAT},'samples':samples}}


class SpeedEstimationTest(unittest.TestCase):
    def test_measures_real_ratios_with_original_frame_brackets_without_rational_rounding(self):
        for ratio in (.5,1.73,2.):
            with self.subTest(ratio=ratio):
                data=scenario(ratio);before=deepcopy(data);result=estimate(data)
                self.assertTrue(result['transitions'])
                change=min(result['transitions'],key=lambda p:abs(p['estimated_transition_seconds']-1002))
                self.assertAlmostEqual(change['speed_multiplier'],ratio,delta=.02)
                self.assertLessEqual(change['speed_ratio_range'][0],ratio)
                self.assertGreaterEqual(change['speed_ratio_range'][1],ratio)
                self.assertAlmostEqual(change['estimated_transition_seconds'],1002,delta=.02)
                self.assertTrue(change['auto_recordable'])
                for state in ('before','after'):
                    self.assertAlmostEqual(change[state]['source_pts_seconds'][0]-change[state]['start'],8000)
                self.assertEqual(data,before)

    def test_repeated_render_frames_do_not_create_changes_in_constant_speed(self):
        self.assertEqual(estimate(scenario(1.,True))['transitions'],[])
        result=estimate(scenario(2.,True))
        self.assertTrue(result['transitions'])
        self.assertTrue(any(c['speed_ratio_range'][0]<=2<=c['speed_ratio_range'][1] for c in result['transitions']))

    def test_missing_support_or_a_capture_gap_cannot_establish_a_transition(self):
        data=scenario()
        for sample in data['scroll_motion']['samples']:sample.update(support=1,lanes=1)
        self.assertEqual(estimate(data)['transitions'],[])
        data=scenario()
        for sample in data['scroll_motion']['samples']:
            if sample['time']>=1002:sample['chunk']=1
        self.assertEqual(estimate(data)['transitions'],[])
        data['scroll_motion']['format']['method']='unregistered_correspondence'
        self.assertEqual(estimate(data)['status'],'unavailable')

    def test_local_capture_distortion_stays_reviewable_instead_of_becoming_metadata(self):
        data=scenario(1)
        for sample in data['scroll_motion']['samples']:
            delta=sample['time']-1002
            if abs(delta)<.5:sample['phase']+=15*math.cos(delta*math.pi)**2
        changes=estimate(data)['transitions']
        self.assertTrue(changes)
        self.assertTrue(any('longer_native_flanks_do_not_confirm_change' in c['review_reasons'] for c in changes))
        self.assertFalse(any(c['auto_recordable'] for c in changes))

    def test_legacy_integrated_coordinates_remain_proposals_without_automatic_registration(self):
        data=scenario();data['scroll_motion'].pop('coordinate_registration')
        result=estimate(data)
        self.assertTrue(result['transitions'])
        self.assertFalse(any(change['auto_recordable'] for change in result['transitions']))
        self.assertTrue(all('joint_native_coordinate_registration_required' in change['review_reasons']
                            for change in result['transitions']))
