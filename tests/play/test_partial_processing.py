"""Clipped pixels may corroborate clear absence, never fabricate a transition."""
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from piu_timeline.play.processing import ReceptorPixels,observe_processing,transition,visible_template
from piu_timeline.play.holds.features import feature_contract


def samples():
    return [{'time':t,'pts':t+40,'y':y,'state':'present'}for t,y in [(0.,30),(.016,25),(.033,22)]]+[
        {'time':.05,'pts':40.05,'y':18,'state':'absent'},
        {'time':.066,'pts':40.066,'y':14,'state':'absent','confirmation_only':True,
         'template_coverage':{'area_fraction':.9,'foreground_fraction':1.}}]


class PartialProcessingTest(unittest.TestCase):
    def test_intersection_preserves_center_and_requires_area_and_foreground(self):
        mask=np.arange(90).reshape(10,9);template=np.ones((7,7),dtype=bool)
        slices,part,coverage=visible_template(mask,template,2,3)
        np.testing.assert_array_equal(mask[slices],mask[0:6,1:8])
        self.assertEqual(part.shape,(6,7));self.assertAlmostEqual(coverage['area_fraction'],6/7)
        self.assertIsNone(visible_template(mask,template,0,3))
        self.assertIsNone(visible_template(mask,template,-20,3))
        template[:]=False;template[0]=True
        self.assertIsNone(visible_template(mask,template,2,3))

    def test_partial_confirmation_preserves_the_full_absence_bracket(self):
        result=transition(samples(),25,10)
        self.assertEqual(result['status'],'disappeared_near_receptor')
        self.assertEqual(result['range'],[.033,.05])
        self.assertEqual(result['source_pts_seconds'],[40.033,40.05])
        self.assertEqual(result['confirmation_source_pts_seconds'],40.066)
        self.assertTrue(result['confirmation_partial_template'])
        for change in ({'area_fraction':.7},{'foreground_fraction':.7}):
            values=samples();values[-1]['template_coverage'].update(change)
            self.assertEqual(transition(values,25,10)['status'],'unresolved')
        values=samples();values[3].update(confirmation_only=True,template_coverage=values[-1]['template_coverage'])
        self.assertEqual(transition(values,25,10)['status'],'unresolved')
        values=samples();values[-1].update(time=.2,pts=40.2)
        self.assertEqual(transition(values,25,10)['status'],'unresolved')
        values=samples();values.insert(4,{'time':.058,'pts':40.058,'y':16,
                                         'state':'unknown','unknown_reason':'partial_head_present'})
        self.assertEqual(transition(values,25,10)['status'],'unresolved')

    def pixel_event(self,kind='clear'):
        layout={'lanes':[{'x':.2+.1*i,'color':'blue'}for i in range(5)],'receptor_y':.142,'note_y_max':.95}
        data={'layout':layout,'media':{},'game_roi':[0,0,325,200],
              'analysis_width':325,'analysis_height':200,'start_seconds':0,'end_seconds':1.4,
              'notes':[{'lane':2,'status':'estimated','target_seconds':1.,'prediction_uncertainty_seconds':.01,
                        'velocity_pixels_per_second':-240.,'points':[]}],
              'hold_analysis':{'holds':[]}}
        pixels=ReceptorPixels(layout,325,200)
        for i in range(84):
            if kind=='truncated'and i==64:break
            t=i/60;y=round(28.4+240*(1-t));image=np.full((200,325,3),70,dtype='uint8')
            if (t<1.04 and 15<=y<185)or kind=='reappeared'and i==64:
                cv2.rectangle(image,(116,y-14),(144,y+14),(255,255,255),-1)
                cv2.rectangle(image,(119,y-11),(141,y+11),(0,130,255),-1)
                if y>28.4+32.5*.85:data['notes'][0]['points'].append([t,y])
            if kind=='flash'and i==64:image[:35,110:150]=255
            if kind=='cut'and i==64:image[:]=0
            pixels.observe(image,t+40,t)
        with tempfile.TemporaryDirectory()as tmp:
            path=Path(tmp)/'pixels.npz';pixels.save(path,feature_contract(data))
            event=observe_processing(data,path)['notes'][0]
        return event

    def test_native_pixel_observation_confirms_once_before_head_leaves_the_crop(self):
        event=self.pixel_event()
        self.assertEqual(event['status'],'disappeared_near_receptor')
        self.assertTrue(event['confirmation_partial_template'])
        self.assertEqual(event['source_pts_seconds'],[40+62/60,40+63/60])
        self.assertEqual(event['confirmation_source_pts_seconds'],40+64/60)
        full_absent=[s for s in event['samples']if s['state']=='absent'and not s.get('confirmation_only')]
        self.assertEqual(len(full_absent),1)

    def test_effect_cut_reappearance_or_missing_confirmation_pixels_cannot_confirm(self):
        for kind in ('flash','cut','reappeared','truncated'):
            with self.subTest(kind=kind):
                event=self.pixel_event(kind)
                self.assertEqual(event['status'],'unresolved')
                self.assertNotIn('range',event)
