"""Source crop phase explains adjacent pixel rows without a wider timing window."""
import unittest

import numpy as np

from piu_timeline.play.processing.registration import centers
from piu_timeline.play.processing.poses import compare
from tests.play.processing.fixtures import edge_flash_frame


def reference():
    mask=np.zeros((13,13),dtype=bool);mask[5:7,3:10]=True
    return {'mask':mask,'poses':[{'mask':mask,'evidence':{'anchor_y_pixels':12.6,'crop_center_y_pixels':13}}]}


class ProcessingRegistrationTest(unittest.TestCase):
    def test_a_clear_registered_shape_is_not_vetoed_by_another_crops_flash(self):
        for radius in (6,8,10):
            with self.subTest(radius=radius):
                color,light,ref,y,r,spacing=edge_flash_frame(radius)
                before=color.copy(),light.copy()
                event=compare(color,light,ref,y,r,spacing)
                self.assertEqual(event['state'],'present')
                self.assertEqual(event['template_vertical_offset_pixels'],1)
                self.assertAlmostEqual(event['score'],.8)
                self.assertTrue(np.array_equal(color,before[0])and np.array_equal(light,before[1]))
                # Shape support and a clear crop are both required.
                weak=color.copy();weak[:round(y)+r-2]=False
                self.assertNotEqual(compare(weak,light,ref,y,r,spacing)['state'],'present')
                flash=compare(color,~color,ref,y,r,spacing)
                self.assertEqual(flash['unknown_reason'],'white_effect')

    def test_direction_comes_from_source_phase_and_never_exceeds_one_pixel(self):
        self.assertEqual(centers(20.2,{}),[20])
        self.assertEqual(centers(20.2,{'anchor_y_pixels':12.6,'crop_center_y_pixels':13}),[20,21])
        self.assertEqual(centers(20.2,{'anchor_y_pixels':12.4,'crop_center_y_pixels':12}),[19,20])
        self.assertEqual(centers(20.,{'anchor_y_pixels':12.,'crop_center_y_pixels':12}),[20])
        with self.assertRaises(ValueError):centers(20.2,{'anchor_y_pixels':12.6,'crop_center_y_pixels':12})

    def test_known_one_pixel_phase_matches_but_distant_shape_does_not(self):
        ref=reference();light=np.zeros((40,13),dtype=bool);color=np.zeros_like(light)
        color[15:28]=ref['mask']  # A center at row 21, with the target at 20.2.
        event=compare(color,light,ref,20.2,6,20)
        self.assertEqual(event['state'],'present')
        self.assertEqual(event['template_vertical_offset_pixels'],1)
        self.assertEqual(event['score'],1.)
        distant=np.zeros_like(color);distant[16:29]=ref['mask']
        self.assertEqual(compare(distant,light,ref,20.2,6,20)['state'],'unknown')
        self.assertEqual(compare(np.zeros_like(color),light,ref,20.2,6,20)['state'],'absent')

    def test_white_effect_at_any_possible_alignment_prevents_clear_absence(self):
        color=np.zeros((40,13),dtype=bool);light=np.zeros_like(color);light[22:28]=True
        event=compare(color,light,reference(),20.2,6,20)
        self.assertEqual(event['state'],'unknown');self.assertEqual(event['unknown_reason'],'white_effect')

    def test_native_position_interval_checks_all_alignments_before_absence(self):
        ref=reference();light=np.zeros((45,13),dtype=bool);color=np.zeros_like(light)
        color[18:31]=ref['mask']  # Actual center 24, outside the nominal center 20.
        self.assertNotEqual(compare(color,light,ref,20.,6,20)['state'],'present')
        event=compare(color,light,ref,20.,6,20,y_range=[18.,24.])
        self.assertEqual(event['state'],'present')
        clear=np.zeros_like(color)
        self.assertEqual(compare(clear,light,ref,20.,6,20,y_range=[18.,24.])['state'],'absent')
        # A flash at any feasible position defeats a claimed clear absence.
        white=light.copy();white[24:28]=True
        self.assertEqual(compare(clear,white,ref,20.,6,20,y_range=[18.,24.])['state'],'unknown')
        self.assertEqual(compare(clear,light,ref,8.,6,20,y_range=[-5.,12.])['state'],'unknown')

    def test_native_position_adapter_retains_all_feasible_vertices(self):
        from piu_timeline.play.scroll_pauses import position_adapter
        model={'kind':'native_interval','origin':1.,'vertices':[[100.,20.],[120.,24.]],
               'representative':[110.,22.],'scale':.5,'start':.8,'end':1.1}
        path=position_adapter({'supported':True,'position_model':model})
        self.assertEqual(path['position_range'](1.),[10.,12.])
        self.assertAlmostEqual(path['position'](1.),11.)
        self.assertIsNone(path['position_range'](1.2));self.assertIsNone(path['position'](1.2))
