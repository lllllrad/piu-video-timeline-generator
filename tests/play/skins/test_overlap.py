"""Generated layered caps; no recording-specific timing or note-count fixtures."""
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from piu_timeline.play.skins.detector import SkinDetector
from tests.play.skins.scenes import bank_at,render


class OverlappingCapsTest(unittest.TestCase):
    def scene(self,root,objects):
        bank=bank_at(root)
        layout={'receptor_y':.05,'lanes':[{'x':(40+i*20)/180}for i in range(5)]}
        detector=SkinDetector(bank,layout,180,300)
        return detector,render(objects,0,180,300,11,None,0)

    def test_stack_retains_each_visible_cap_without_a_separate_clearance_gap(self):
        with tempfile.TemporaryDirectory()as temporary:
            objects=[{'lane':0,'y':y,'kind':'tap'}for y in (90,102,114,126)]
            detector,image=self.scene(Path(temporary),objects)
            caps=[c for c in detector.detect(image)if c['role']!='hold_body']
            self.assertEqual([round(c['y']*300)for c in caps],[90,102,114,126])
            recovered=[c for c in caps if c.get('occlusion_evidence')]
            self.assertEqual(len(recovered),3)
            for cap in recovered:
                self.assertTrue(cap['occlusion_evidence']['foreground_caps'])
                self.assertGreater(cap['occlusion_evidence']['visible_cap_pixels'],0)
                self.assertEqual(cap['role'],'unknown') # Hidden connectors remain unknown.

    def test_two_stacks_in_different_lanes_never_share_ownership(self):
        with tempfile.TemporaryDirectory()as temporary:
            objects=[{'lane':lane,'y':y,'kind':'tap'}for lane in (0,2)for y in (90,102,114)]
            detector,image=self.scene(Path(temporary),objects)
            caps=[c for c in detector.detect(image)if c['role']!='hold_body']
            self.assertEqual([(c['lane'],round(c['y']*300))for c in caps],[(lane,y)for lane in(0,2)for y in(90,102,114)])

    def test_overlapping_artwork_from_an_adjacent_lane_keeps_both_lane_identities(self):
        from tests.play.skins.scenes import cap
        with tempfile.TemporaryDirectory()as temporary:
            bank=bank_at(Path(temporary));bank['reference_frame']={'kind':'full_game_crop','width':180,'height':300}
            layout={'receptor_y':.05,'lanes':[{'x':(40+i*14)/180}for i in range(5)]}
            detector=SkinDetector(bank,layout,180,300)
            image=np.zeros((300,180,3),dtype='uint8')
            image[90:110,30:50]=cap(0);image[90:110,44:64]=cap(1)
            caps=[c for c in detector.detect(image)if c['role']!='hold_body']
            self.assertEqual([(c['lane'],round(c['y']*300))for c in caps],[(0,100),(1,100)])
            proof=caps[0]['occlusion_evidence']['foreground_caps']
            self.assertTrue(any(c['lane']==1 for c in proof))

    def test_layering_survives_different_game_scales_and_overlap_depths(self):
        for scale in(.5,1,1.5,2):
            for distance in(8,12,16):
                with self.subTest(scale=scale,distance=distance),tempfile.TemporaryDirectory()as temporary:
                    objects=[{'lane':0,'y':90+i*distance,'kind':'tap'}for i in range(3)]
                    detector,image=self.scene(Path(temporary),objects)
                    width,height=round(180*scale),round(300*scale)
                    detector=SkinDetector(detector.bank,detector.layout,width,height)
                    image=cv2.resize(image,(width,height),interpolation=cv2.INTER_AREA)
                    caps=[c for c in detector.detect(image)if c['role']!='hold_body']
                    self.assertEqual(len(caps),3)
                    for actual,expected in zip(caps,objects,strict=True):
                        self.assertLessEqual(abs(actual['y']*height-expected['y']*scale),.5)

    def test_unexplained_obstruction_cannot_be_removed_as_an_occluding_note(self):
        with tempfile.TemporaryDirectory()as temporary:
            objects=[{'lane':0,'y':100,'kind':'tap'}]
            detector,image=self.scene(Path(temporary),objects)
            image[100:110,30:50]=[80,10,170] # No positively measured foreground cap.
            caps=[c for c in detector.detect(image)if c['role']!='hold_body']
            self.assertEqual(caps,[])

    def test_visible_connector_can_confirm_a_partially_hidden_hold_cap(self):
        with tempfile.TemporaryDirectory()as temporary:
            objects=[{'lane':0,'y':100,'end_y':180,'kind':'hold'},
                     {'lane':0,'y':90,'kind':'tap'}]
            detector,image=self.scene(Path(temporary),objects)
            caps=[c for c in detector.detect(image)if c['role']!='hold_body']
            start=next(c for c in caps if round(c['y']*300)==100)
            self.assertEqual(start['role'],'hold_start')
            self.assertTrue(start.get('occlusion_evidence'))
            self.assertNotIn('connection',start.get('unavailable_regions',[]))

    def test_fully_hidden_cap_does_not_gain_fabricated_observations(self):
        with tempfile.TemporaryDirectory()as temporary:
            detector,image=self.scene(Path(temporary),[{'lane':0,'y':100,'kind':'tap'}for _ in range(3)])
            caps=[c for c in detector.detect(image)if c['role']!='hold_body']
            self.assertEqual(len(caps),1)

    def test_role_and_support_consumers_retain_the_visible_footprint_and_original_pts(self):
        from piu_timeline.play.skins.sampling import key
        from piu_timeline.play.skins.support import cap_support
        from piu_timeline.play.skins.observations import observe
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary)
            detector,image=self.scene(root,[{'lane':0,'y':y,'kind':'tap'}for y in(90,102)])
            caps=[c for c in detector.detect(image)if c['role']!='hold_body'];partial=caps[0]
            support=cap_support(detector.by_sampling[key(partial)],partial)
            self.assertEqual(int(support.sum()),partial['occlusion_evidence']['visible_cap_pixels'])
            data={'analysis_width':180,'analysis_height':300,'layout':detector.layout,
                'notes':[{'lane':0,'points':[(1.5,partial['y']*300)]}],
                'skin_detector':{'bank_path':str(root/'bank.json'),'contract':{'bank':detector.bank['contract']}}}
            roles=observe(data,[{'playback_seconds':1.5,'source_pts_seconds':42.125,'skin_observations':caps}])
            proof=roles['notes'][0]['observations'][0]
            self.assertEqual(proof['source_pts_seconds'],42.125)
            self.assertEqual(proof['occlusion_evidence'],partial['occlusion_evidence'])
            self.assertEqual(proof['visible_cap_runs'],partial['visible_cap_runs'])
            self.assertEqual(roles['notes'][0]['status'],'unknown')

    def test_a_single_cap_does_not_seed_a_chain_of_extra_caps(self):
        with tempfile.TemporaryDirectory()as temporary:
            detector,image=self.scene(Path(temporary),[{'lane':0,'y':100,'kind':'tap'}])
            caps=[c for c in detector.detect(image)if c['role']!='hold_body']
            self.assertEqual([round(c['y']*300)for c in caps],[100])

    def test_partial_connector_requires_visible_support_in_every_spatial_cell(self):
        from tests.play.skins.test_detector import examples
        from piu_timeline.play.skins.bank import load_bank
        from piu_timeline.play.skins.overlap import recovery_record
        from piu_timeline.play.skins.coverage import ReferenceRows,image_spans
        for role in ('hold_start','hold_end'):
            with self.subTest(role=role),tempfile.TemporaryDirectory()as temporary:
                root=Path(temporary);items,_=examples(root)
                layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1}for i in range(5)]}
                detector=SkinDetector(load_bank(root/'bank.json'),layout,200,300)
                template=next(t for t in detector.templates if t['id']==role)
                source=next(rgb for name,rgb,_,_ in items if name==role)
                image=np.zeros((300,200,3),dtype='uint8');image[80:115,10:30]=source
                image=image.astype('float32')/255
                # A thin measured neighboring stroke crosses cap and connector.
                known=np.zeros((300,200),bool);known[80:115,16]=True
                image[known]=[.9,.2,.7]
                record=recovery_record(detector,image,template,0,10,80,known,[])
                self.assertIsNotNone(record);self.assertEqual(record['role'],role)
                self.assertTrue(record['visible_connection_runs'])
                self.assertTrue(all(a>6 for _,a,_ in record['visible_connection_runs']))
                rows=image_spans(record,ReferenceRows('body'))
                expected=range(102,115)if role=='hold_start'else range(80,92)
                self.assertEqual({y for a,b in rows for y in range(a,b)},set(expected))
                from piu_timeline.play.skins.observations import observe
                data={'analysis_width':200,'analysis_height':300,'layout':layout,
                    'skin_detector':{'bank_path':str(root/'bank.json'),'contract':{'bank':detector.bank['contract']}},
                    'notes':[{'lane':0,'points':[[1.25,record['y']*300]]}]}
                channel=observe(data,[{'playback_seconds':1.25,'source_pts_seconds':31.25,
                                      'skin_observations':[record]}])
                proof=channel['notes'][0]['observations'][0]
                self.assertEqual(proof['visible_connection_runs'],record['visible_connection_runs'])
                self.assertEqual(proof['source_pts_seconds'],31.25)
                # Foreground concealing one whole spatial cell is insufficient.
                blocked=known.copy();blocked[80:115,16:19]=True
                self.assertEqual(recovery_record(detector,image,template,0,10,80,blocked,[])['role'],'unknown')
                # Unexplained corruption in still-visible body stays a failure.
                damaged=image.copy()
                a,b,c,d=next(r['box']for r in template['regions']if r['name']=='connection')
                damaged[80+b:80+d,20:24]=[.9,.2,.7]
                self.assertEqual(recovery_record(detector,damaged,template,0,10,80,known,[])['role'],'unknown')
                # Without independently measured foreground, no pixels are excluded.
                absent=np.zeros_like(known)
                self.assertIsNone(recovery_record(detector,image,template,0,10,80,absent,[]))

    def test_hidden_connector_rows_do_not_become_positive_body_support(self):
        from tests.play.skins.test_detector import examples
        from piu_timeline.play.skins.bank import load_bank
        from piu_timeline.play.skins.overlap import recovery_record
        from piu_timeline.play.skins.coverage import ReferenceRows,image_spans
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);items,_=examples(root)
            layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1}for i in range(5)]}
            detector=SkinDetector(load_bank(root/'bank.json'),layout,200,300)
            template=next(t for t in detector.templates if t['id']=='hold_end')
            image=np.zeros((300,200,3),dtype='uint8');image[80:115,10:30]=items[2][1]
            known=np.zeros((300,200),bool);known[100:115,16]=True;known[85,16:24]=True
            image=image.astype('float32')/255;image[known]=[.9,.2,.7]
            record=recovery_record(detector,image,template,0,10,80,known,[])
            self.assertEqual(record['role'],'hold_end')
            rows=image_spans(record,ReferenceRows('body'))
            self.assertEqual({y for a,b in rows for y in range(a,b)},set(range(80,92))-{85})

    def test_partial_connector_never_relaxes_required_terminal_features(self):
        from tests.play.skins.test_detector import examples
        from piu_timeline.play.skins.bank import load_bank
        from piu_timeline.play.skins.overlap import recovery_record
        import json
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);items,document=examples(root)
            end=next(t for t in document['templates']if t['role']=='hold_end')
            end['cap_features']=['terminal'];end['regions'].append(
                {'name':'terminal','box':[0,31,20,35],'maximum_error':.001})
            (root/'bank.json').write_text(json.dumps(document))
            layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1}for i in range(5)]}
            detector=SkinDetector(load_bank(root/'bank.json'),layout,200,300)
            template=next(t for t in detector.templates if t['id']=='hold_end')
            image=np.zeros((300,200,3),dtype='uint8');image[80:115,10:30]=items[2][1]
            known=np.zeros((300,200),bool);known[80:115,16]=True
            self.assertIsNone(recovery_record(detector,image.astype('float32')/255,template,0,10,80,known,[]))


if __name__=='__main__':unittest.main()
