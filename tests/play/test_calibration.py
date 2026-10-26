import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import numpy as np
from piu_timeline.play.layout import validate_layout, recover_layout
import unittest

from piu_timeline.play.layout import combine_receptor_observations


class CalibrationTest(unittest.TestCase):
    def test_fixed_positions_select_mode_and_side_without_observing_flashes(self):
        from piu_timeline.play.layout import fixed_layout
        left = fixed_layout({'chart': 'S23', 'players': {'p1': {}}})
        right = fixed_layout({'chart': 'S15', 'players': {'p2': {}}})
        double = fixed_layout({'chart': 'D24'})
        self.assertEqual(len(left['lanes']), 5)
        self.assertLess(max(lane['x'] for lane in left['lanes']), .5)
        self.assertGreater(min(lane['x'] for lane in right['lanes']), .5)
        self.assertEqual(len(double['lanes']), 10)
        self.assertEqual(fixed_layout({'chart':'HD17'})['profile'],'double')
        self.assertEqual(fixed_layout({'chart':'HS9','players':{'p2':{}}})['profile'],'single_p2')
        self.assertEqual(left['receptor_y'], right['receptor_y'])
        self.assertEqual(left['method'], 'fixed_phoenix_game_layout')
        self.assertIsNone(fixed_layout({'chart': 'S23'}))
        self.assertIsNone(fixed_layout({'chart': None, 'players': {'p1': {}}}))
        self.assertIsNone(fixed_layout({'chart': 'S23', 'players': {'p1': {}, 'p2': {}}}))
        self.assertEqual(fixed_layout({'chart': 'S23'}, 'p2'), right)

    def test_complementary_partial_frames_recover_only_repeatedly_observed_lanes(self):
        centers=[(300+77*i,103) for i in range(10)]
        seen=[([p for i,p in enumerate(centers) if i not in missing],{'source_pts_seconds':time})
              for missing,time in [({3,4},1),({1,6},2),({7,8},3)]]
        result=combine_receptor_observations(seen,1300,730,10)
        self.assertEqual(result,centers)
        # A missing lane cannot be filled in from presumed equal spacing.
        absent=[([p for p in points if p != centers[5]],meta) for points,meta in seen]
        self.assertIsNone(combine_receptor_observations(absent,1300,730,10))

    def test_repeated_copies_of_one_timestamp_and_irregular_grids_are_rejected(self):
        centers=[(300+77*i,103) for i in range(10)]
        repeated=[(centers,{'source_pts_seconds':1})]*3
        self.assertIsNone(combine_receptor_observations(repeated,1300,730,10))
        centers[5]=(750,103)
        self.assertIsNone(combine_receptor_observations([(centers,{'source_pts_seconds':t}) for t in [1,2]],1300,730,10))

    def test_short_native_window_breaks_repeated_beat_flash_sampling(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import numpy as np
        from piu_timeline.play.layout import recover_layout
        centers=[(40+12*i,14) for i in range(10)]
        ordinary=np.zeros((100,200,3),dtype='uint8')
        staggered=ordinary.copy();staggered[0,0,0]=1
        def partial(image):
            missing={0,1} if image[0,0,0] else {3,4}
            return [p for i,p in enumerate(centers) if i not in missing]
        decoded=[(100+i*.017,i*.017,staggered) for i in range(4)]
        with tempfile.TemporaryDirectory() as temporary:
            preview=Path(temporary)/'segment/preview.png';preview.parent.mkdir()
            calibration={'source_pts_seconds':1}
            with patch('piu_timeline.play.layout.fixed_layout',return_value=None), \
                    patch('piu_timeline.play.layout.receptor_centers',side_effect=partial), \
                    patch('piu_timeline.play.layout.capture_game',side_effect=lambda record,path,t,roi:{'source_pts_seconds':t+200}), \
                    patch('piu_timeline.play.layout.cv2.imread',return_value=ordinary), \
                    patch('piu_timeline.play.layout.decode_frames',return_value=iter(decoded)):
                layout=recover_layout({},(0,0,200,100),{'chart':'D20','start_seconds':0,'end_seconds':60},preview,ordinary,calibration)
        self.assertEqual(layout['method'],'corroborated_partial_receptor_outlines')
        self.assertEqual(len(layout['lanes']),10)
        support=calibration['supporting_frames']
        self.assertEqual([item['source_pts_seconds'] for item in support[-2:]],[100,100.051])

    def test_shared_geometry_requires_current_spread_out_receptor_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);old=root/'segment-001';old.mkdir()
            pending=root/'segment-002.build-test';pending.mkdir()
            layout={'receptor_y':.14,'lanes':[{'x':.1+.08*i} for i in range(10)]}
            record={'path':'source.mkv'};roi=[0,0,100,100]
            (old/'analysis.json').write_text(json.dumps({'media':record,'game_roi':roi,'layout':layout}))
            points=[(100*layout['lanes'][i]['x'],14) for i in (0,3,6,9)]
            with patch('piu_timeline.play.layout.fixed_layout',return_value=None), \
                    patch('piu_timeline.play.layout.receptor_centers',return_value=points), \
                    patch('piu_timeline.play.layout.locate_layout',side_effect=ValueError('masked')), \
                    patch('piu_timeline.play.layout.capture_game',side_effect=AssertionError('already verified')):
                result=recover_layout(record,roi,{'chart':'D20'},pending/'preview.png',
                                      np.zeros((100,100,3),dtype='uint8'),{'source_pts_seconds':100})
            self.assertEqual(result['method'],'corroborated_shared_geometry')
            self.assertEqual(result['lanes'],layout['lanes'])

    def test_invalid_layout_fails_before_pixel_processing(self):
        with self.assertRaises(ValueError):
            validate_layout({'lanes': []})
        with self.assertRaises(ValueError):
            validate_layout({'lanes': [{'x': float('nan'), 'color': 'blue'}] * 5})

    def test_moving_heads_resolve_unknown_mode_without_inventing_a_chart_level(self):
        import cv2
        from piu_timeline.play.layout_evidence import MovingHeadProfiles
        from piu_timeline.play.layout import SINGLE_X
        def frame(y, lanes=(0,2,4)):
            image=np.zeros((400,650,3),dtype='uint8')
            for lane in lanes:
                x=round(SINGLE_X['p2'][lane]*650)
                color=(255,255,0) if lane==2 else (0,130,255)
                cv2.rectangle(image,(x-14,y-14),(x+14,y+14),(255,255,255),-1)
                cv2.rectangle(image,(x-11,y-11),(x+11,y+11),color,-1)
            return image
        segment={'chart':None,'players':{'p2':{}}}
        profiles=MovingHeadProfiles(segment)
        for pts,y in [(1,180),(2,160)]:self.assertIsNone(profiles.observe(frame(y),{'source_pts_seconds':pts}))
        layout=profiles.observe(frame(140),{'source_pts_seconds':3})
        self.assertEqual(layout['profile'],'single_p2')
        self.assertEqual(profiles.latest_support(),3)
        self.assertEqual(segment['chart'],None)
        for kind in ('same_pts','stationary','only_one_lane','wrong_mode'):
            profiles=MovingHeadProfiles({'chart':'D24','players':{'p2':{}}} if kind=='wrong_mode' else segment)
            for i in range(4):
                image=frame(180 if kind=='stationary' else 180-i*20,(0,) if kind=='only_one_lane' else (0,2,4))
                self.assertIsNone(profiles.observe(image,{'source_pts_seconds':1 if kind=='same_pts' else i}))

    def test_native_calibration_follows_observed_heads_after_an_empty_intro(self):
        import cv2
        from piu_timeline.play.layout import SINGLE_X
        def image(y=None):
            rgb=np.zeros((400,650,3),dtype='uint8')
            if y is not None:
                for lane in (0,2,4):
                    x=round(SINGLE_X['p2'][lane]*650)
                    cv2.rectangle(rgb,(x-14,y-14),(x+14,y+14),(255,255,255),-1)
                    cv2.rectangle(rgb,(x-11,y-11),(x+11,y+11),(0,130,255),-1)
            return rgb
        def capture(record,path,seconds,roi):
            cv2.imwrite(str(path),cv2.cvtColor(image(180 if seconds==34 else None),cv2.COLOR_RGB2BGR))
            return {'source_pts_seconds':seconds,'playback_seconds':seconds}
        def decode(record,start,end,roi,width):
            self.assertAlmostEqual(start,34.137)
            return iter((start+i/20,start+i/20,image(180-i*5)) for i in range(7))
        with tempfile.TemporaryDirectory() as temp:
            preview=Path(temp)/'preview.png';cv2.imwrite(str(preview),image())
            with patch('piu_timeline.play.layout.capture_game',side_effect=capture), \
                    patch('piu_timeline.play.layout.decode_frames',side_effect=decode):
                layout=recover_layout({},(0,0,650,400),
                    {'chart':None,'players':{'p2':{}},'start_seconds':0,'end_seconds':60},
                    preview,image(),{'source_pts_seconds':0})
            self.assertEqual(layout['profile'],'single_p2')
