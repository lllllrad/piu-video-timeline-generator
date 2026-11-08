"""A known cap appearance needs its own positive, unoccluded role context."""
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


class SharedRoleTest(unittest.TestCase):
    def fixture(self,root,role='hold_start',feature=False,share=True):
        items,document=examples(root)
        source=next(rgb.copy()for name,rgb,_,_ in items if name==role)
        entry=deepcopy(next(t for t in document['templates']if t['id']==role))
        a,b,c,d=entry['regions'][0]['box'];source[b:d,a:c]=255-source[b:d,a:c]
        cv2.imwrite(str(root/'appearance.png'),np.dstack([source[:,:,::-1],np.full(source.shape[:2],255,dtype='uint8')]))
        entry.update(id='appearance',image='appearance.png',role='tap',regions=[entry['regions'][0]])
        document['templates'].append(entry)
        if feature:
            context=next(t for t in document['templates']if t['id']==role)
            context['cap_features']=['terminal'];context['regions'].append({'name':'terminal','box':[a,d-4,c,d],'maximum_error':.001})
        if share:document['shared_cap_families']=[{'id':'common','appearance_templates':['appearance'],'role_templates':[role]}]
        (root/'bank.json').write_text(json.dumps(document))
        layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1}for i in range(5)]}
        detector=SkinDetector(load_bank(root/'bank.json'),layout,200,300)
        image=np.zeros((300,200,3),dtype='uint8');image[80:80+len(source),10:30]=source
        return detector,image,document

    def test_known_appearance_and_independent_connection_establish_start(self):
        with tempfile.TemporaryDirectory()as temporary:
            detector,image,_=self.fixture(Path(temporary))
            caps=[c for c in detector.detect(image)if c['role']!='hold_body']
            self.assertEqual(len(caps),1);cap=caps[0]
            self.assertEqual(cap['role'],'hold_start');self.assertEqual(cap['template'],'appearance')
            self.assertEqual(cap['shared_role']['context']['template'],'hold_start')
            # Blank tap margins must never become positive body coverage.
            all_rows=ReferenceRows('all');body_rows=ReferenceRows('body');cap_rows=ReferenceRows('cap')
            self.assertEqual(image_spans(cap,all_rows),[(80,100),(102,115)])
            self.assertEqual(image_spans(cap,body_rows),[(102,115)])
            self.assertEqual(image_spans(cap,cap_rows),[(80,100)])

    def test_role_from_an_alternative_cap_retains_native_evidence_metadata(self):
        from piu_timeline.play.observations.cache import validate_native_frame
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);_,image,document=self.fixture(root)
            alias=deepcopy(next(t for t in document['templates']if t['id']=='appearance'))
            alias['id']='alternate-appearance';document['templates'].append(alias)
            document['shared_cap_families'][0]['appearance_templates']=['alternate-appearance']
            (root/'bank.json').write_text(json.dumps(document))
            layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1}for i in range(5)]}
            detector=SkinDetector(load_bank(root/'bank.json'),layout,200,300)
            observations=detector.detect(image);caps=[r for r in observations if r['role']!='hold_body']
            self.assertEqual(len(caps),1);self.assertEqual(caps[0]['role'],'hold_start')
            self.assertEqual(caps[0]['template'],'alternate-appearance')
            self.assertEqual(caps[0]['method'],'skin_image')
            validate_native_frame({'source_pts_seconds':31.25,'playback_seconds':1.25,
                'combo':None,'notes':caps,'skin_observations':observations},5)

    def test_missing_connection_cannot_be_replaced_with_a_known_cap(self):
        with tempfile.TemporaryDirectory()as temporary:
            detector,image,_=self.fixture(Path(temporary))
            image[100:115]=0
            caps=[c for c in detector.detect(image)if c['role']!='hold_body']
            self.assertEqual(len(caps),1);self.assertEqual(caps[0]['role'],'unknown')

    def test_no_implicit_sharing_without_a_skin_declaration(self):
        with tempfile.TemporaryDirectory()as temporary:
            detector,image,_=self.fixture(Path(temporary),share=False)
            caps=[c for c in detector.detect(image)if c['role']!='hold_body']
            self.assertEqual(len(caps),1);self.assertEqual(caps[0]['role'],'unknown')

    def test_shared_appearance_does_not_bypass_a_required_tail_feature(self):
        with tempfile.TemporaryDirectory()as temporary:
            detector,image,_=self.fixture(Path(temporary),role='hold_end',feature=True)
            caps=[c for c in detector.detect(image)if c['role']!='hold_body']
            self.assertEqual(len(caps),1);self.assertEqual(caps[0]['role'],'unknown')

    def test_body_fallback_requires_every_connector_pixel_at_this_cap(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);_,image,document=self.fixture(root)
            document['shared_cap_families'][0]['body_templates']=['hold_body']
            reference=cv2.imread(str(root/'hold_start.png'),cv2.IMREAD_UNCHANGED)
            reference[22:35,6:14,:3]=[30,60,220] # Wrong reference neck appearance.
            cv2.imwrite(str(root/'hold_start.png'),reference)
            (root/'bank.json').write_text(json.dumps(document))
            layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1}for i in range(5)]}
            detector=SkinDetector(load_bank(root/'bank.json'),layout,200,300)
            cap=next(c for c in detector.detect(image)if c['role']!='hold_body')
            self.assertEqual(cap['role'],'hold_start')
            proof=cap['shared_role']['context']['body_coverage']
            self.assertEqual(proof['method'],'positive_body_reference_coverage')
            self.assertEqual(proof['covered_pixels'],8*13)
            self.assertGreater(proof['reference_region_error'],.001)
            # A remote correct body and a break at the neck cannot prove a hold.
            image[108:115]=0;image[170:182,16:24]=[25,140,210]
            cap=next(c for c in detector.detect(image)if c['role']!='hold_body')
            self.assertEqual(cap['role'],'unknown')

    def test_changed_body_references_invalidate_dependent_cap_classification(self):
        from piu_timeline.play.skins.reuse import reusable_groups
        from piu_timeline.play.skins.detector import FORMAT
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);old=root/'old';new=root/'new';old.mkdir();new.mkdir()
            for path in (old,new):
                _,_,document=self.fixture(path)
                document['shared_cap_families'][0]['body_templates']=['hold_body']
                (path/'bank.json').write_text(json.dumps(document))
            before=load_bank(old/'bank.json')
            body=cv2.imread(str(new/'hold_body.png'),cv2.IMREAD_UNCHANGED)
            body[0,0,0]+=1;cv2.imwrite(str(new/'hold_body.png'),body)
            data={'skin_detector':{'bank_path':str(old/'bank.json'),
                'contract':{'bank':before['contract'],'detector':FORMAT}}}
            self.assertNotIn('caps/0',reusable_groups(data,load_bank(new/'bank.json')))
            # The same body edit does not invalidate caps with no declared dependency.
            for path in (old,new):
                document=json.loads((path/'bank.json').read_text())
                document['shared_cap_families'][0].pop('body_templates')
                (path/'bank.json').write_text(json.dumps(document))
            data['skin_detector']['contract']['bank']=load_bank(old/'bank.json')['contract']
            self.assertIn('caps/0',reusable_groups(data,load_bank(new/'bank.json')))

    def test_shared_context_uses_only_the_visible_part_of_each_connector_cell(self):
        from piu_timeline.play.skins.shared_roles import contexts
        with tempfile.TemporaryDirectory()as temporary:
            detector,image,_=self.fixture(Path(temporary))
            cap=next(c for c in detector.detect(image)if c['role']=='hold_start')
            template=next(t for t in detector.templates if t['id']=='hold_start')
            rgb=image.astype('float32')/255;hidden=np.zeros((300,200),bool)
            hidden[102:115,16]=True;rgb[hidden]=[.9,.2,.7]
            body=(np.zeros_like(hidden),[])
            result=contexts(detector,rgb,cap,template,hidden,body)
            self.assertIsNotNone(result);self.assertEqual(result['visible_connection_pixels'],7*13)
            self.assertIsNone(contexts(detector,rgb,cap,template,np.zeros_like(hidden),body))
            hidden[102:115,16:19]=True
            self.assertIsNone(contexts(detector,rgb,cap,template,hidden,body))

    def test_a_family_cannot_share_across_lanes_or_missing_references(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);_,_,document=self.fixture(root)
            for wrong in ('absent','hold_body'):
                document['shared_cap_families'][0]['appearance_templates']=[wrong]
                (root/'bank.json').write_text(json.dumps(document))
                with self.assertRaises(ValueError):load_bank(root/'bank.json')
            document['shared_cap_families'][0]['appearance_templates']=['appearance']
            next(t for t in document['templates']if t['id']=='appearance')['lane_kind']=1
            (root/'bank.json').write_text(json.dumps(document))
            with self.assertRaises(ValueError):load_bank(root/'bank.json')
