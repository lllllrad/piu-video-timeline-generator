import unittest

from piu_timeline.play_analysis import combine_receptor_observations


class CalibrationTest(unittest.TestCase):
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
        from piu_timeline.play_analysis import recover_layout
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
            with patch('piu_timeline.play_analysis.receptor_centers',side_effect=partial), \
                    patch('piu_timeline.play_analysis.capture_game',side_effect=lambda record,path,t,roi:{'source_pts_seconds':t+200}), \
                    patch('piu_timeline.play_analysis.cv2.imread',return_value=ordinary), \
                    patch('piu_timeline.play_analysis.decode_frames',return_value=iter(decoded)):
                layout=recover_layout({},(0,0,200,100),{'chart':'D20','start_seconds':0,'end_seconds':60},preview,ordinary,calibration)
        self.assertEqual(layout['method'],'corroborated_partial_receptor_outlines')
        self.assertEqual(len(layout['lanes']),10)
        support=calibration['supporting_frames']
        self.assertEqual([item['source_pts_seconds'] for item in support[-2:]],[100,100.051])
