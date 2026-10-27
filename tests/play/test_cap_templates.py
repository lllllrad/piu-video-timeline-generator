"""Connected-cap coordinates need independent references and a unique match."""
import unittest

import numpy as np

from piu_timeline.play.cap_templates import learn,match,sums
from tests.play.test_head_registration import patch


def reference():
    white=patch()[1]
    return {'image':white[32:66,15:50].copy(),'bounds':[15,32,35,34],
            'support':{0:{'note':0},1:{'note':1}}}


class CapTemplateTest(unittest.TestCase):
    def test_connected_body_does_not_move_matching_cap_or_create_a_tap_label(self):
        masks=patch();masks[0,:32,20:45]=True;masks[3,:32,20:45]=True
        result=match(np.packbits(masks,axis=-1),65,34,0,[reference()],2)
        self.assertIsNotNone(result)
        self.assertEqual(result['offset_pixels'],-1.)
        self.assertAlmostEqual(result['similarity'],1.)
        self.assertNotIn('kind',result)
        # The caller retains fractional-to-integer patch conversion.
        self.assertEqual(match(np.packbits(masks,axis=-1),65,34,-.5,[reference()],2)['offset_pixels'],-1.5)

    def test_self_reference_effect_and_clipped_cap_are_not_evidence(self):
        packed=np.packbits(patch(),axis=-1)
        self.assertIsNone(match(packed,65,34,0,[reference()],0))
        masks=patch();masks[1,:,:]=True
        self.assertIsNone(match(np.packbits(masks,axis=-1),65,34,0,[reference()],2))
        masks=patch();masks[4,30:68,10:55]=False
        self.assertIsNone(match(np.packbits(masks,axis=-1),65,34,0,[reference()],2))
        masks=patch();masks[0,:,:]=False
        self.assertIsNone(match(np.packbits(masks,axis=-1),65,34,0,[reference()],2))

    def test_same_glyph_with_different_supported_origins_is_ambiguous(self):
        first=reference();second={**reference(),'image':np.pad(first['image'],((2,0),(0,0))),
                                 'bounds':[15,30,35,36]}
        self.assertIsNone(match(np.packbits(patch(),axis=-1),65,34,0,[first,second],2))

    def test_reference_bank_needs_two_distinct_heads_and_preserves_dense_frame_identity(self):
        masks=np.array([np.packbits(patch(),axis=-1)]*3)
        # Two same-lane heads in one frame have different native positions.
        pixels={'masks':masks,'columns':65,'pts':np.array([30.,30.,30.2]),'ys':np.array([150.,220.,150.])}
        lookup={(0.,0):[0,1],(.2,0):[2]}
        records=[{'note':i,'lane':0,'status':'registered','offset_pixels':-1.,
                  'observations':[{'time':t,'source_pts_seconds':pts,'detected_y_pixels':y,
                                   'offset_pixels':-1.,'outer_bounds_in_patch':[15,32,35,34]}]}
                 for i,t,pts,y in [(0,0.,30.,150.),(1,0.,30.,220.),(2,.2,30.2,150.)]]
        self.assertEqual(learn(records[:1],pixels,lookup)[0],[])
        templates=learn(records,pixels,lookup)[0]
        self.assertEqual(len(templates),1)
        self.assertEqual(set(templates[0]['support']),{0,1,2})
        changed=[{**r,'lane':i}for i,r in enumerate(records)]
        other_lookup={(0.,0):[0],(0.,1):[1],(.2,2):[2]}
        self.assertTrue(all(not bank for bank in learn(changed,pixels,other_lookup).values()))

    def test_integral_counts_match_each_candidate_patch(self):
        image=np.arange(35).reshape(5,7)%3==0
        expected=np.array([[image[y:y+2,x:x+3].sum()for x in range(5)]for y in range(4)])
        np.testing.assert_array_equal(sums(image,2,3),expected)
