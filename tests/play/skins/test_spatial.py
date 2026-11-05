"""Connector proof must follow all of its artwork, not one horizontal probe."""
from pathlib import Path
import tempfile
import unittest

import numpy as np

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.matching import RegionSearch,prepare_regions
from piu_timeline.play.skins.sampling import models
from piu_timeline.play.skins.spatial import cells
from tests.play.skins.test_detector import examples


class SpatialConnectionTest(unittest.TestCase):
    def test_side_damage_cannot_average_into_a_positive_connection(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);examples(root)
            original=next(t for t in load_bank(root/'bank.json')['templates']if t['role']=='hold_start')
            original['regions'][1]['maximum_error']=.03
            template=next(models(original,1));prepare_regions(template)
            image=template['rgb'].copy();h,w=image.shape[:2]
            good=RegionSearch(image).evaluate(template,[0,0,w,h])
            self.assertLessEqual(good[0][0,0],1)
            # Leave the center row and center column intact. A small broken
            # shoulder passes the old whole-region average, but is not a hold.
            image[22:26,6:8]=np.minimum(1,image[22:26,6:8]+.4)
            region=template['regions'][1];search=RegionSearch(image)
            self.assertLess(search.error(template,region,[0,0,w,h])[0,0],.03)
            measured=search.evaluate(template,[0,0,w,h])
            self.assertLessEqual(measured[1][0,0],1) # The cap remains observed.
            self.assertGreater(measured[0][0,0],1)

    def test_disconnected_shoulders_are_checked_without_requiring_center_pixels(self):
        mask=np.zeros((12,18),dtype='uint8');mask[:4,:4]=1;mask[8:,14:]=1
        parts=list(cells({'name':'connection','box':[3,5,21,17],'mask':mask}))
        rebuilt=np.zeros_like(mask)
        for part in parts:
            a,b,c,d=part['box'];rebuilt[b-5:d-5,a-3:c-3]|=part['mask']
        np.testing.assert_array_equal(rebuilt,mask)
        self.assertEqual(len(parts),2)


if __name__=='__main__':unittest.main()
