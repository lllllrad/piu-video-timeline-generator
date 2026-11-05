"""Weighted search agrees with direct RGB comparisons of each visible mask."""
import unittest
import numpy as np

from piu_timeline.play.skins.visible_search import VisibleSearch


class VisibleSearchTest(unittest.TestCase):
    def test_masked_rgb_error_matches_direct_enumeration_for_every_position(self):
        rng=np.random.default_rng(420)
        image=rng.random((24,28,3),dtype='float32');rgb=rng.random((9,10,3),dtype='float32')
        mask=(rng.random((5,6))>.25).astype('uint8')
        template={'rgb':rgb,'mask':np.ones((9,10),dtype='uint8'),
            'regions':[{'name':'cap','box':[2,1,8,6],'mask':mask}]}
        for fraction in(0,.3,.8,1):
            with self.subTest(foreground_fraction=fraction):
                known=rng.random((24,28))<fraction
                error,count=VisibleSearch(image,known).error(template,[3,2,24,21])
                for row in range(error.shape[0]):
                    for col in range(error.shape[1]):
                        visible=mask.astype(bool)&~known[3+row:8+row,5+col:11+col]
                        self.assertEqual(count[row,col],visible.sum())
                        if visible.any():
                            expected=np.square((image[3+row:8+row,5+col:11+col]-rgb[1:6,2:8])[visible]).mean()
                            self.assertAlmostEqual(float(error[row,col]),float(expected),places=5)
