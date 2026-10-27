"""Persistence learns clear same-head pixels, never a HUD-covered silhouette."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from piu_timeline.play.processing import ReceptorPixels,observe_processing
from piu_timeline.play.processing.templates import learn,hud_regions
from piu_timeline.play.pixel_cache import native_measurements,source_contract


def fixture(root):
    source=root/'source.mkv';source.write_bytes(b'unchanged recording')
    layout={'lanes':[{'x':.2+.1*i,'color':'blue'}for i in range(5)],'receptor_y':.142,
            'note_y_max':.95,'combo_roi':[.34,.52,.12,.075],'judgment_roi':[.34,.32,.12,.19]}
    data={'layout':layout,'media':{'path':str(source)},'game_roi':[0,0,325,200],
          'analysis_width':325,'analysis_height':200,'start_seconds':0,'end_seconds':1.4,
          'notes':[{'lane':2,'status':'estimated','target_seconds':1.,'prediction_uncertainty_seconds':.01,
                    'velocity_pixels_per_second':-240.,'points':[]}],'hold_analysis':{'holds':[]}}
    decoded=[]
    for i in range(84):
        t=i/60;y=round(28.4+240*(1-t));image=np.full((200,325,3),70,dtype='uint8')
        if t<1 and 15<=y<185:
            cv2.rectangle(image,(116,y-14),(144,y+14),(255,255,255),-1)
            cv2.rectangle(image,(119,y-11),(141,y+11),(0,130,255),-1)
            if y>28.4+32.5*.85:data['notes'][0]['points'].append([t,y])
        image[74:86,116:145]=255  # Known judgment foreground in the old learning band.
        decoded.append((42+t,t,image))
    pixels=ReceptorPixels(layout,325,200)
    for pts,time,planes,_ in native_measurements(data,root,lambda *args:iter(decoded)):
        pixels.observe_masks(planes,pts,time)
    pixels.save(root/'processing-features.npz',source_contract(data))
    return data,np.array([t for _,t,_ in decoded]),np.array([p for p,_,_ in decoded])


class ProcessingTemplateTest(unittest.TestCase):
    def test_full_approach_supplies_clear_reference_when_band_is_inside_known_hud(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);data,times,pts=fixture(root);original=deepcopy(data)
            reference=learn(data,root,times,pts)[0]
            self.assertGreaterEqual(reference['evidence']['frames'],3)
            points={round(t+42,6):y for t,y in data['notes'][0]['points']}
            for p in reference['evidence']['source_pts_seconds']:
                self.assertEqual(hud_regions(data['layout'],2,points[round(p,6)],15,325,200),[])
            event=observe_processing(data,root/'processing-features.npz')['notes'][0]
            self.assertEqual(event['status'],'disappeared_near_receptor')
            self.assertEqual(event['source_pts_seconds'],[42+59/60,43.])
            self.assertEqual(event['template_evidence'],reference['evidence'])
            # No missing full-frame cache may make the old masked band acceptable.
            (root/'native-features/manifest.json').unlink()
            self.assertEqual(observe_processing(data,root/'processing-features.npz')['notes'][0]['reason'],
                             'insufficient_clear_approach')
            self.assertEqual(data,original)
            self.assertEqual((root/'source.mkv').read_bytes(),b'unchanged recording')

    def test_hud_only_observations_or_short_tracks_do_not_supply_a_template(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);data,times,pts=fixture(root)
            data['notes'][0]['points']=[p for p in data['notes'][0]['points']if 65<=p[1]<=90]
            self.assertEqual(learn(data,root,times,pts),{})
            data['notes'][0]['points']=data['notes'][0]['points'][:2]
            self.assertEqual(learn(data,root,times,pts),{})

    def test_mismatched_native_timestamps_or_source_contract_fail_explicitly(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);data,times,pts=fixture(root)
            for changed_times,changed_pts in ((times+.01,pts),(times,pts+.01),(times[:-1],pts[:-1])):
                with self.assertRaisesRegex(ValueError,'Processing template native'):
                    learn(data,root,changed_times,changed_pts)
            data['media']['path']='another recording'
            with self.assertRaisesRegex(ValueError,'source/geometry contract'):learn(data,root,times,pts)
