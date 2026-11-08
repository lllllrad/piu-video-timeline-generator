"""Distinct terminal artwork identifies an end, independently of connection coverage."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from tests.play.skins.test_detector import examples
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.coverage import ReferenceRows,image_spans
from piu_timeline.play.skins.held import BodyAtReceptor
from piu_timeline.play.skins.observations import observe


class DistinctRoleTest(unittest.TestCase):
    def fixture(self,root,declared=True):
        items,document=examples(root)
        pixels=cv2.imread(str(root/'hold_end.png'),cv2.IMREAD_UNCHANGED)
        pixels[15:35,:,:3]=255-pixels[15:35,:,:3]
        cv2.imwrite(str(root/'hold_end.png'),pixels)
        if declared:document['templates'][2]['cap_role_identification']='distinct_full_cap'
        (root/'bank.json').write_text(json.dumps(document))
        layout={'receptor_y':.28,'lanes':[{'x':.1+i*.1}for i in range(5)]}
        detector=SkinDetector(load_bank(root/'bank.json'),layout,200,300)
        image=np.zeros((300,200,3),dtype='uint8');image[80:115,10:30]=pixels[:,:,:3][:,:,::-1]
        return detector,image,items,document

    def test_distinct_full_tail_does_not_require_a_second_body_comparison_to_identify_its_kind(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);detector,image,_,_=self.fixture(root)
            image[80:95]=0 # No positive connector; the terminal glyph is complete.
            observed=detector.detect(image);caps=[o for o in observed if o['role']!='hold_body']
            self.assertEqual(len(caps),1);end=caps[0]
            self.assertEqual((end['role'],end['classification_status']),('hold_end','cap_role_pattern'))
            self.assertGreater(end['region_errors']['connection'],.001)
            self.assertEqual(image_spans(end,ReferenceRows('body')),[])
            self.assertFalse(BodyAtReceptor(detector)(observed))
            data={'analysis_width':200,'analysis_height':300,'layout':detector.layout,
                  'skin_detector':{'bank_path':str(root/'bank.json'),'contract':{'bank':detector.bank['contract']}},
                  'notes':[{'lane':0,'points':[[1.25,105.]]}]}
            channel=observe(data,[{'playback_seconds':1.25,'source_pts_seconds':31.25,'skin_observations':observed}])
            proof=channel['notes'][0]['observations'][0]
            self.assertEqual(proof['role'],'hold_end');self.assertFalse(proof['role_evidence']['connection_confirmed'])
            self.assertEqual(proof['source_pts_seconds'],31.25)

    def test_the_declaration_does_not_invent_body_support_or_change_complete_matches(self):
        with tempfile.TemporaryDirectory()as temporary:
            detector,image,_,_=self.fixture(Path(temporary))
            end=next(o for o in detector.detect(image)if o['role']=='hold_end')
            self.assertEqual(end['classification_status'],'full_pattern')
            self.assertNotIn('role_evidence',end)

    def test_undeclared_or_partial_terminal_patterns_remain_unresolved(self):
        with tempfile.TemporaryDirectory()as temporary:
            detector,image,items,_=self.fixture(Path(temporary),declared=False);image[80:95]=0
            self.assertFalse(any(o['role']=='hold_end'for o in detector.detect(image)))
        with tempfile.TemporaryDirectory()as temporary:
            detector,image,items,_=self.fixture(Path(temporary));image[80:95]=0
            image[105:125,10:30]=items[1][1][:20] # Another actual cap hides the terminal.
            self.assertFalse(any(o['role']=='hold_end'for o in detector.detect(image)))

    def test_plain_taps_and_start_glyphs_do_not_match_the_distinct_tail(self):
        with tempfile.TemporaryDirectory()as temporary:
            detector,_,items,_=self.fixture(Path(temporary))
            for source in (items[0][1],items[1][1]):
                image=np.zeros((300,200,3),dtype='uint8');image[100:100+len(source),10:30]=source
                self.assertFalse(any(o['role']=='hold_end'for o in detector.detect(image)))

    def test_invalid_kind_declarations_are_rejected(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);_,_,_,document=self.fixture(root)
            for index,value in [(0,'distinct_full_cap'),(3,'distinct_full_cap'),(2,True),(2,'guess')]:
                altered=deepcopy(document);altered['templates'][index]['cap_role_identification']=value
                (root/'bank.json').write_text(json.dumps(altered))
                with self.assertRaises(ValueError):load_bank(root/'bank.json')
