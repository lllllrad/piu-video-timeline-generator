"""A held interval can outlast the visible field without an invented head."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector,FORMAT
from piu_timeline.play.skins.holds import reconstruct_images as reconstruct
from tests.play.skins.test_detector import examples


def reconstruct_images(*args,**kwargs):
    return reconstruct(*args,**kwargs)['holds']


def fixture(root,tap=False):
    items,_=examples(root);bank=load_bank(root/'bank.json')
    layout={'receptor_y':.05,'note_y_max':.95,'lanes':[{'x':.1+i*.1,'color':'blue'}for i in range(5)]}
    detector=SkinDetector(bank,layout,200,300);native=[];receptors=[];points=[[],[]];motion=[]
    def paste(image,y,patch):
        a,b=max(0,y),min(300,y+len(patch))
        if a<b:image[a:b,10:10+patch.shape[1]]=patch[a-y:b-y]
    for index in range(133):
        time=index*.025;head=280-5*index;tail=head+360
        image=np.zeros((300,200,3),dtype='uint8')
        a,b=max(0,head+10),min(300,tail-10)
        if a<b:image[a:b,16:24]=[25,140,210]
        paste(image,head-10,items[1][1]);paste(image,tail-25,items[2][1])
        if tap and index==60:paste(image,130,items[0][1])
        observations=detector.detect(image)
        for i,y in enumerate((head,tail)):
            if any(o['role']!='hold_body'and abs(o['y']*300-y)<1e-6 for o in observations):points[i].append([time,y])
        native.append({'playback_seconds':time,'source_pts_seconds':40+time,'skin_observations':observations})
        receptors.append({'playback_seconds':time,'source_pts_seconds':40+time,'receptor_lit':[None]*5})
        motion.append({'time':time,'source_pts':40+time,'phase':200*time,'chunk':0,'support':2 if index else 0,
                       'coordinate_status':'joint_registered'})
    notes=[{'lane':0,'points':p,'status':'estimated','target_seconds':t,'prediction_uncertainty_seconds':.02,
            'velocity_pixels_per_second':-200}for p,t in zip(points,(1.325,3.125))]
    if tap:notes.append({'lane':0,'points':[[1.5,150]],'status':'excluded','target_seconds':None})
    data={'analysis_width':200,'analysis_height':300,'layout':layout,'notes':notes,'start_seconds':0.,'end_seconds':3.3,
          'game_roi':[0,0,200,300],'scroll_motion':{'samples':motion},
          'skin_detector':{'bank_path':str(root/'bank.json'),'contract':{'bank':bank['contract'],'detector':FORMAT}}}
    return data,native,receptors


class TemporalHoldTest(unittest.TestCase):
    def test_longer_than_the_field_uses_positive_regions_and_measured_edges(self):
        with tempfile.TemporaryDirectory()as temporary:
            data,native,receptors=fixture(Path(temporary));original=deepcopy((data,native,receptors))
            self.assertFalse(set(dict(data['notes'][0]['points']))&set(dict(data['notes'][1]['points'])))
            warnings=[];holds=reconstruct_images(data,receptors,native,warnings)
            self.assertEqual(len(holds),1)
            hold=holds[0]
            self.assertEqual((hold['head_note'],hold['tail_note']),(0,1))
            self.assertEqual(hold['start_range'],[1.305,1.345])
            self.assertEqual(hold['end_range'],[3.105,3.145])
            self.assertEqual(hold['body_evidence'],'skin_temporal_image_regions')
            self.assertTrue(any(p.get('connected_to')for p in hold['image_connection_evidence']))
            self.assertTrue(all(p['trace']=='frames.jsonl'for p in hold['image_connection_evidence']))
            self.assertFalse(any('head_y'in p and 'tail_y'in p for p in hold['image_connection_evidence']))
            for i in (0,1):
                cap_pts=hold['component_evidence'][str(i)]['source_pts_seconds']
                self.assertTrue(set(cap_pts).issubset({40+t for t,y in data['notes'][i]['points']}))
                self.assertNotIn(41.5,cap_pts)
            self.assertEqual((data,native,receptors),original)

    def test_missing_images_or_motion_and_competing_identity_do_not_bridge_silently(self):
        with tempfile.TemporaryDirectory()as temporary:
            original,source,receptors=fixture(Path(temporary))
            for case in ('missing_image','missing_motion','second_head'):
                data,native=deepcopy(original),deepcopy(source)
                if case=='missing_image':native[60]['skin_observations']=[]
                elif case=='missing_motion':data['scroll_motion']['samples'][60]['support']=0
                else:data['notes'].append(deepcopy(data['notes'][0]))
                warnings=[]
                with self.subTest(case=case):
                    self.assertEqual(reconstruct_images(data,receptors,native,warnings),[])
                    self.assertTrue(warnings)

    def test_clear_lost_body_rows_warn_while_documented_hud_can_explain_them(self):
        with tempfile.TemporaryDirectory()as temporary:
            data,native,receptors=fixture(Path(temporary))
            def touches(image):
                patterns=[image,*image.get('alternatives',[])]
                return any(p['bounds_pixels'][1]<170 and p['bounds_pixels'][3]>150 for p in patterns)
            native[60]['skin_observations']=[o for o in native[60]['skin_observations']if not touches(o)]
            warnings=[];holds=reconstruct_images(data,receptors,native,warnings)
            self.assertEqual(len(holds),1)
            self.assertTrue(any(p['time']==1.5 and p.get('missing_intervals_pixels')
                                for w in warnings for p in w.get('image_evidence',[])))
            from piu_timeline.play.skins.holds import covered
            at_gap=[p['covered_bounds_pixels']for p in holds[0]['image_connection_evidence']if p['time']==1.5]
            self.assertFalse(covered(150,170,at_gap))
            with patch('piu_timeline.play.screen_regions.note_occluders',return_value=[{'id':'judgment','rect':[.05,.4,.1,.3]}]):
                explained=[];self.assertEqual(len(reconstruct_images(data,receptors,native,explained)),1)
            self.assertFalse(any(p['time']==1.5 and p.get('missing_intervals_pixels')
                                 for w in explained for p in w.get('image_evidence',[])))

    def test_a_positive_tap_between_body_islands_refutes_the_interval(self):
        with tempfile.TemporaryDirectory()as temporary:
            data,native,receptors=fixture(Path(temporary),tap=True)
            self.assertTrue(any(o['role']=='tap'and abs(o['y']*300-150)<1e-6 for o in native[60]['skin_observations']))
            warnings=[]
            self.assertEqual(reconstruct_images(data,receptors,native,warnings),[])
            self.assertTrue(warnings)
