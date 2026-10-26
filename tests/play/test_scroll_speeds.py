"""Typed relative speed transitions must agree with native geometry."""
from copy import deepcopy
import unittest

from piu_timeline.charts.gimmicks import validate_candidates
from piu_timeline.play.gimmicks import apply_gimmicks
from piu_timeline.play.processing_motion import observed_path
from piu_timeline.play.scroll_speeds import classify_warnings


def effect():
    return {'id':'change','kind':'scroll_speed_change','review_status':'pending','reason':'Two stable native clocks',
            'start_seconds':.5,'end_seconds':1.6,'playback_start_seconds':.5,'playback_end_seconds':1.6,
            'speed_multiplier':2.,'speed_ratio_range':[1.9,2.1],'transition_range_seconds':[.9,1.1]}


class ScrollSpeedTest(unittest.TestCase):
    def test_measured_piecewise_motion_supports_pixels_but_does_not_restore_chart_or_input(self):
        points=[]
        for i in range(36,85):
            time=i/60;delta=time-1
            points.append([time,240-200*(delta if delta<0 else 2*delta)])
        note={'lane':0,'status':'excluded','target_seconds':None,'points':points}
        data={'analysis_height':400,'layout':{'note_y_max':.95},'notes':[note],'matches':[],
              'chart_policy':{'gimmick_candidates':[effect()]}}
        original=deepcopy(data);view=apply_gimmicks(data)
        path=observed_path(note,view,40,40,1)
        self.assertTrue(path['supported'])
        self.assertEqual(path['basis'],'configured_speed_native_trajectory')
        self.assertAlmostEqual(path['target'],1.5)
        self.assertAlmostEqual(path['position'](.8),280.)
        self.assertAlmostEqual(path['position'](1.2),160.)
        self.assertIsNone(view['notes'][0]['target_seconds'])
        self.assertEqual(view['matches'],[])
        self.assertEqual(data,original)
        note['points']=[[t,240-200*(t-1)] for t,_ in points]
        self.assertFalse(observed_path(note,view,40,40,1)['supported'])

    def test_only_matching_measured_changes_are_accounted_for(self):
        data=apply_gimmicks({'chart_policy':{'gimmick_candidates':[effect()]}})
        matching={'reason':'scroll_speed_change','visible_start_seconds':.95,'visible_end_seconds':1.05,
                  'velocity_before_pixels_per_second':-200,'velocity_after_pixels_per_second':-400,
                  'velocity_error_before':5,'velocity_error_after':5}
        different={**matching,'velocity_after_pixels_per_second':-100}
        outside={**matching,'visible_start_seconds':3,'visible_end_seconds':3.1}
        uncertain={**matching,'velocity_error_before':250}
        warnings,expected=classify_warnings(data,[matching,different,outside,uncertain])
        self.assertEqual(warnings,[different,outside,uncertain])
        self.assertEqual(expected[0]['native_reason'],'scroll_speed_change')
        data['chart_policy']['gimmick_candidates'][0]['review_status']='rejected'
        self.assertEqual(apply_gimmicks(data)['scroll_speed_model'],[])

    def test_ambiguous_ratio_or_outside_boundary_is_invalid_metadata(self):
        validate_candidates({'gimmick_candidates':[effect()]})
        for key,value in [('speed_ratio_range',[.8,2.1]),('speed_multiplier',0),('speed_multiplier',False),
                          ('transition_range_seconds',[.1,.2]),('speed_ratio_range',[float('nan'),2])]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_candidates({'gimmick_candidates':[{**effect(),key:value}]})
