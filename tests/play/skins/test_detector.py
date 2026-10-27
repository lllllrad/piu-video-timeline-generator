"""Direct RGB location and endpoint context work without white contours."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector,occluded_support
from piu_timeline.play.tracking import NoteTracker


def examples(root):
    rng = np.random.default_rng(11)
    cap = rng.integers(40, 160, (20, 20, 3), dtype='uint8')
    body = np.full((12, 8, 3), [25, 140, 210], dtype='uint8')
    start = np.zeros((35, 20, 3), dtype='uint8'); start[:20] = cap; start[20:, 6:14] = body[0]
    end = np.zeros((35, 20, 3), dtype='uint8'); end[15:] = cap; end[:15, 6:14] = body[0]
    items = [('tap', cap, [10, 10], [{'name':'cap','box':[0,0,20,20]}]),
             ('hold_start', start, [10, 10], [{'name':'cap','box':[0,0,20,20]}, {'name':'connection','box':[6,22,14,35]}]),
             ('hold_end', end, [10, 25], [{'name':'cap','box':[0,15,20,35]}, {'name':'connection','box':[6,0,14,12]}]),
             ('hold_body', body, [4, 6], [{'name':'body','box':[0,0,8,12]}])]
    entries = []
    for role, rgb, anchor, regions in items:
        alpha = np.full(rgb.shape[:2], 255, dtype='uint8')
        if role in ('hold_start', 'hold_end'):
            alpha[:]=0
            for region in regions:
                x0,y0,x1,y1=region['box'];alpha[y0:y1,x0:x1]=255
        cv2.imwrite(str(root / (role+'.png')), np.dstack([rgb[:,:,::-1],alpha]))
        entries.append({'id':role,'role':role,'lane_kind':0,'image':role+'.png',
                        'anchor_pixels':anchor,'regions':[{**r,'maximum_error':.001}for r in regions]})
    manifest={'schema':1,'skin':'synthetic','spacing_pixels':20,'templates':entries}
    (root/'bank.json').write_text(json.dumps(manifest))
    return items,manifest


class SkinDetectorTest(unittest.TestCase):
    def test_transparent_padding_cannot_hide_clear_cap_and_connection_pixels(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);items,_=examples(root);bank=load_bank(root/'bank.json')
            layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1,'color':'blue'}for i in range(5)]}
            image=np.zeros((300,200,3),dtype='uint8');end=items[2][1];image[90:125,10:30]=end
            clear={'id':'combo','rect':[.05,.30,.025,.04]}
            with patch('piu_timeline.play.skins.detector.note_occluders',return_value=[clear]):
                result=SkinDetector(bank,layout,200,300).detect(image)
            self.assertTrue(any(o['role']=='hold_end'and abs(o['y']*300-115)<1e-6 for o in result))
            for rect in ([.08,.30,.04,.04],[.05,.35,.1,.05]):
                with patch('piu_timeline.play.skins.detector.note_occluders',return_value=[{'id':'hud','rect':rect}]):
                    blocked=SkinDetector(bank,layout,200,300).detect(image)
                self.assertFalse(any(o['role']=='hold_end'and abs(o['y']*300-115)<1e-6 for o in blocked))
            support=np.zeros((10,10),dtype=bool);support[4,4]=True
            with patch('piu_timeline.play.skins.detector.note_occluders',return_value=[{'id':'hud','rect':[.145,.145,.001,.001]}]):
                self.assertTrue(occluded_support({},support,10,10,100,100))

    def test_image_scan_finds_caps_and_distinguishes_body_above_from_body_below(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);items,_=examples(root);bank=load_bank(root/'bank.json')
            layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1,'color':'blue'}for i in range(5)]}
            image=np.zeros((300,200,3),dtype='uint8')
            for role,rgb,anchor,_ in items:
                if role=='hold_body':continue
                y={'tap':60,'hold_start':130,'hold_end':220}[role]
                top=y-anchor[1];image[top:top+rgb.shape[0],10:10+rgb.shape[1]]=rgb
            with patch('cv2.findContours',side_effect=AssertionError('Contour candidates are forbidden')):
                tracker=NoteTracker(layout,200,300,skin_bank=bank)
                found=tracker.detect(image)
            self.assertEqual([(r['role'],round(r['y']*300,6))for r in found],
                             [('tap',60),('hold_start',130),('hold_end',220)])
            self.assertTrue(tracker.hold_candidate)
            self.assertTrue(all('connection'in r['region_errors']for r in found if r['role']!='tap'))
            # Identical cap pixels cannot make the connected end an extra tap.
            self.assertEqual(sum(abs(r['y']*300-220)<2 for r in found),1)
            detector=SkinDetector(bank,layout,200,300)
            image[195:207,16:24]=0
            changed=detector.detect(image)
            self.assertFalse(any(r['role']=='hold_end'and abs(r['y']*300-220)<2 for r in changed))

    def test_connection_region_cannot_be_omitted_or_placed_on_wrong_side(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);_,manifest=examples(root)
            for case in ('missing','wrong_side','empty_mask'):
                changed=deepcopy(manifest);template=changed['templates'][2]
                if case=='missing':template['regions']=template['regions'][:1]
                elif case=='wrong_side':template['anchor_pixels'][1]=5
                else:
                    path=root/'hold_end.png';rgba=cv2.imread(str(path),cv2.IMREAD_UNCHANGED)
                    rgba[:15,:,3]=0;cv2.imwrite(str(path),rgba)
                (root/'bank.json').write_text(json.dumps(changed))
                with self.subTest(case=case),self.assertRaises(ValueError):load_bank(root/'bank.json')

    def test_pixel_changes_invalidate_bank_identity_and_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);_,manifest=examples(root);first=load_bank(root/'bank.json')['contract']
            path=root/'tap.png';rgba=cv2.imread(str(path),cv2.IMREAD_UNCHANGED);rgba[0,0,0]+=1
            cv2.imwrite(str(path),rgba)
            self.assertNotEqual(first,load_bank(root/'bank.json')['contract'])
            manifest['templates'][0]['image']='../elsewhere.png'
            (root/'bank.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):load_bank(root/'bank.json')
