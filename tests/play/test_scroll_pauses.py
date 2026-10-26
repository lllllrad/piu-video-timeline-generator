"""Generic paused-motion models, strict evidence and unchanged input/chart truth."""
from copy import deepcopy
import unittest

from piu_timeline.charts.gimmicks import validate_candidates
from piu_timeline.play.gimmicks import apply_gimmicks
from piu_timeline.play.processing_motion import observed_path
from piu_timeline.play.scroll_pauses import classify_warnings, moving_time


def effect():
    return {'id':'pause','kind':'scroll_pause','review_status':'pending','reason':'Observed stationary heads with live background',
            'start_seconds':1.,'end_seconds':1.5,'playback_start_seconds':1.,'playback_end_seconds':1.5,
            'pause_duration_seconds':.5,'speed_multiplier':0,'boundary_uncertainty_seconds':.02}


class ScrollPauseTest(unittest.TestCase):
    def test_pause_coordinates_reinterpret_pixels_without_restoring_failed_chart_timing(self):
        times=[i/60 for i in range(48,111)]
        points=[[t,40+200*(1.5-moving_time([t],[{'start':1.,'end':1.5}])[0])] for t in times]
        note={'lane':0,'status':'excluded','reason':'shared_timing_reconstruction_failed','target_seconds':None,'points':points}
        data={'analysis_height':400,'layout':{'note_y_max':.95},'notes':[note],'matches':[],
              'chart_policy':{'gimmick_candidates':[effect()]}}
        before=deepcopy(data);view=apply_gimmicks(data)
        path=observed_path(note,view,40,40,1)
        self.assertTrue(path['supported'])
        self.assertEqual(path['basis'],'configured_pause_native_trajectory')
        self.assertAlmostEqual(path['target'],2.)
        self.assertAlmostEqual(path['position'](1.1),path['position'](1.4))
        self.assertAlmostEqual(path['position'](1.7),100.)
        self.assertIsNone(view['notes'][0]['target_seconds'])
        self.assertEqual(view['matches'],[])
        self.assertEqual(data,before)
        # A contradictory measured moving head must not be forced stationary.
        wrong=deepcopy(note)
        wrong['points']=[[t,40+200*(2-t)] for t in times]
        self.assertFalse(observed_path(wrong,view,40,40,1)['supported'])
        view['chart_policy']['gimmick_candidates'][0]['review_status']='rejected'
        self.assertEqual(apply_gimmicks(view)['scroll_pause_model'],[])

    def test_stationary_and_edge_records_are_classified_but_other_changes_still_warn(self):
        data=apply_gimmicks({'chart_policy':{'gimmick_candidates':[effect()]}})
        stopped={'reason':'possible_scroll_stop_or_capture_freeze','visible_start_seconds':1.1,'visible_end_seconds':1.4}
        speed={'reason':'scroll_speed_change','visible_start_seconds':.95,'visible_end_seconds':1.05,
               'velocity_before_pixels_per_second':-200,'velocity_after_pixels_per_second':0,
               'velocity_error_before':10,'velocity_error_after':10}
        unrelated={**speed,'velocity_after_pixels_per_second':-400}
        outside={**stopped,'visible_start_seconds':1.6,'visible_end_seconds':1.8}
        warnings,expected=classify_warnings(data,[stopped,speed,unrelated,outside])
        self.assertEqual(warnings,[unrelated,outside])
        self.assertEqual(len(expected),2)
        self.assertEqual(expected[0]['native_reason'],stopped['reason'])
        self.assertEqual(expected[0]['gimmick_candidates'],['pause'])

    def test_inconsistent_or_overlapping_pause_metadata_is_rejected(self):
        validate_candidates({'gimmick_candidates':[effect()]})
        for field,value in [('pause_duration_seconds',.1),('speed_multiplier',.1),('boundary_uncertainty_seconds',1.),
                            ('boundary_uncertainty_seconds',float('nan')),('speed_multiplier',False)]:
            candidate={**effect(),field:value}
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                validate_candidates({'gimmick_candidates':[candidate]})
        with self.assertRaisesRegex(ValueError,'overlap'):
            validate_candidates({'gimmick_candidates':[effect(),{**effect(),'id':'other'}]})

    def test_declared_pause_replays_pixels_to_find_disappearance_without_creating_input(self):
        import json
        from pathlib import Path
        import tempfile
        import cv2
        import numpy as np
        from piu_timeline.play.processing import ReceptorPixels
        from piu_timeline.play.pixel_cache import source_contract
        layout={'lanes':[{'x':.2+.1*i,'color':'blue'} for i in range(5)],'receptor_y':.3,'note_y_max':.95}
        candidate={**effect(),'start_seconds':.4,'end_seconds':.7,'playback_start_seconds':.4,
                   'playback_end_seconds':.7,'pause_duration_seconds':.3}
        note={'lane':2,'status':'excluded','reason':'shared_timing_reconstruction_failed','target_seconds':None,'points':[]}
        data={'layout':layout,'media':{},'game_roi':[0,0,325,200],'analysis_width':325,'analysis_height':200,
              'start_seconds':0,'end_seconds':1.6,'notes':[note],'matches':[],
              'chart_policy':{'gimmick_candidates':[candidate]},'hold_analysis':{'holds':[]},'visual_channels':{}}
        pixels=ReceptorPixels(layout,325,200)
        for i in range(96):
            t=i/60;y=round(60+200*(.8-moving_time([t],[{'start':.4,'end':.7}])[0]))
            rgb=np.full((200,325,3),70,dtype='uint8')
            if t<1.1 and 15<=y<185:
                cv2.rectangle(rgb,(116,y-14),(144,y+14),(255,255,255),-1)
                cv2.rectangle(rgb,(119,y-11),(141,y+11),(0,130,255),-1)
                if y>60+.85*32.5:note['points'].append([t,y])
            pixels.observe(rgb,t+100,t)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pixels.save(root/'processing-features.npz',source_contract(data))
            native=deepcopy(data);view=apply_gimmicks(data,root)
            record=view['visual_channels']['processing']['notes'][0]
            self.assertEqual(record['status'],'disappeared_near_receptor')
            self.assertEqual(record['motion_basis'],'configured_pause_native_trajectory')
            self.assertAlmostEqual(record['range'][1],1.1)
            self.assertAlmostEqual(record['source_pts_seconds'][1],101.1)
            self.assertIsNone(view['notes'][0]['target_seconds'])
            self.assertEqual(view['matches'],[])
            self.assertEqual(data,native)
