"""A body's approach visibility is distinct from its recognition interval."""
from copy import deepcopy
import unittest

from piu_timeline.play.holds.input_risk import hold_overlap
from piu_timeline.play.skins.held import FORMAT


def evidence():
    return {'skin_detector':{'contract':{'held_body':FORMAT},'missing_template_roles':[]},
            'unsupported_intervals':[], 'hold_analysis':{'holds':[{
                'id':0,'head_note':2,'tail_note':3,'lane':1,'start_range':[1.3,1.31],'end_range':[1.5,1.51],
                'start_censored':False,'end_censored':False,'body_frames':8,'body_evidence':'skin_start_body_end_images'}],
                'unresolved_tracks':[{'hold':0,'note':2,'tail_note':3,'lane':1,
                    'failure_detail':'known_hold_image_connection_not_observed_in_clear_frames',
                    'visible_start_seconds':.8,'visible_end_seconds':1.2}]}}


class HoldRiskTest(unittest.TestCase):
    def test_linked_visibility_warning_keeps_the_known_cap_bounds_and_is_not_removed(self):
        data=evidence();original=deepcopy(data)
        self.assertFalse(hold_overlap(data,1.,1.04,.034))
        self.assertTrue(hold_overlap(data,1.32,1.35,.034))
        self.assertEqual(data,original)

    def test_unknown_or_unproven_connections_and_native_risk_remain_blocking(self):
        for case in ('wrong_tail','missing_cap','censored','unsupported_geometry','old_profile','native_body'):
            with self.subTest(case=case):
                data=evidence();hold=data['hold_analysis']['holds'][0]
                if case=='wrong_tail':hold['tail_note']=4
                elif case=='missing_cap':hold['head_note']=None
                elif case=='censored':hold['start_censored']=True
                elif case=='unsupported_geometry':hold['body_frames']=3
                elif case=='old_profile':data['skin_detector']['contract']['held_body']={}
                else:data['unsupported_intervals']=[{'start_seconds':1.,'end_seconds':1.1}]
                self.assertTrue(hold_overlap(data,1.,1.04,.034))
