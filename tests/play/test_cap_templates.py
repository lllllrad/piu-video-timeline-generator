"""Connected-cap coordinates need independent references and a unique match."""
import unittest
from copy import deepcopy

import numpy as np

from piu_timeline.play.cap_templates import learn,match,sums,refine_outlines
from piu_timeline.play.head_registration import fit_offset
from tests.play.test_head_registration import patch


def reference():
    white=patch()[1]
    return {'image':white[32:66,15:50].copy(),'bounds':[15,32,35,34],
            'support':{0:{'note':0},1:{'note':1}}}


class CapTemplateTest(unittest.TestCase):
    def refinement(self):
        times=np.arange(10)*.02
        pixels={'masks':np.array([np.packbits(patch(),axis=-1)]*10),'columns':65,
                'spacing':34,'times':times,'pts':times+20,'ys':np.full(10,150.)}
        samples=[{'time':float(t),'source_pts_seconds':float(t+20),'detected_y_pixels':150.,
                  'offset_pixels':-1. if i<9 else 2.,'patch_center_shift_pixels':0.,
                  'outer_bounds_in_patch':[15,32,35,34]if i<9 else [15,38,35,28]}
                 for i,t in enumerate(times)]
        record={'note':2,'lane':0,**fit_offset(samples)}
        data={'analysis_width':400,'analysis_height':400,
              'layout':{'receptor_y':.1,'lanes':[{'x':.3}]}}
        lookup={(round(float(t),6),0):[i]for i,t in enumerate(times)}
        return data,pixels,lookup,{0:[reference()]},[record]

    def test_independent_whole_cap_corrects_truncated_contour_without_discarding_frames(self):
        data,pixels,lookup,banks,records=self.refinement();before=deepcopy(records)
        self.assertEqual(records[0]['status'],'unresolved')
        result=refine_outlines(data,pixels,lookup,banks,records,fit_offset)[0]
        self.assertEqual(records,before)
        self.assertEqual(result['status'],'registered')
        self.assertEqual(len(result['observations']),10)
        corrected=result['observations'][-1]
        self.assertEqual(corrected['offset_pixels'],-1.)
        self.assertEqual(corrected['outline_observation'],before[0]['observations'][-1])
        self.assertEqual(corrected['source_pts_seconds'],20.18)
        self.assertEqual(corrected['outer_bounds_in_patch'],[15,32,35,34])
        self.assertNotIn('target_seconds',corrected)

    def test_uncertain_self_referenced_hidden_or_mismatched_pixels_do_not_erase_conflicts(self):
        for case in ('self','effect','hud','pts','real_shift','shifted_box'):
            with self.subTest(case=case):
                data,pixels,lookup,banks,records=self.refinement()
                if case=='self':banks[0][0]['support'][2]={'note':2}
                elif case=='hud':data['layout'].update(combo_roi=[.2,.3,.3,.2])
                elif case=='pts':pixels['pts'][-1]+=1
                elif case=='effect':
                    masks=patch();masks[1]=True;pixels['masks'][-1]=np.packbits(masks,axis=-1)
                elif case=='shifted_box':records[0]['observations'][-1]['outer_bounds_in_patch']=[15,35,35,34]
                else:
                    pixels['masks'][-1]=np.packbits(np.roll(patch(),3,axis=1),axis=-1)
                result=refine_outlines(data,pixels,lookup,banks,records,fit_offset)[0]
                self.assertEqual(result['status'],'unresolved')
                self.assertEqual(len(result['observations']),10)
                self.assertEqual(len(result['conflicting_observations']),1)

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
