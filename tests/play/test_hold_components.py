"""White-border repair must preserve the identity of its original foreground."""
import unittest

import numpy as np

from piu_timeline.play.holds.features import detect_bodies


class HoldComponentTest(unittest.TestCase):
    def test_repaired_body_retains_three_original_stripes_and_their_native_bounds(self):
        layout={'receptor_y':.15,'lanes':[{'x':.38+.06*i,'color':'blue'}for i in range(5)]}
        image=np.zeros((183,325,3),dtype='uint8');x=round(.5*325)
        image[70:112,x-5:x+6]=(0,130,255)
        image[82,x-5:x+6]=255;image[99,x-5:x+6]=255
        bodies,_=detect_bodies(image,layout)
        merged=next(b for b in bodies if b['lane']==2 and b['white_cap_bridge'])
        middle=next(b for b in bodies if b['lane']==2 and not b['white_cap_bridge'])
        self.assertEqual(merged['foreground_bounds'],[x-5,70,x+6,112])
        self.assertEqual(middle['foreground_bounds'],[x-5,83,x+6,99])
        self.assertEqual(len(merged['source_components']),3)
        self.assertEqual(len(middle['source_components']),1)
        self.assertLess(set(middle['source_components']),set(merged['source_components']))
        # A separate colored cap adds an actual component, not a duplicate ID.
        image[45:62,x-5:x+6]=(0,130,255)
        extended,_=detect_bodies(image,layout)
        cap=next(b for b in extended if b['lane']==2 and b['top']==45)
        repaired=next(b for b in extended if b['lane']==2 and b['white_cap_bridge'])
        self.assertTrue(set(cap['source_components']).isdisjoint(repaired['source_components']))
