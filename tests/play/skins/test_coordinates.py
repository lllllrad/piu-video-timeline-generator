"""Direct cap measurements participate in geometry without inventing calibration."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.play.beats.coordinates import prepare
from piu_timeline.play.spacing_checks import spacing_failures
from piu_timeline.play.head_registration import apply
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.coordinates import measure,cap_reference
from tests.play.skins.coordinate_fixtures import clock_fixture
from tests.play.skins.test_detector import examples


def fixture(root):
    _,manifest=examples(root)
    original=manifest['templates'][0];manifest['templates']=[{**original,'id':f'tap-{lane}','lane_kind':lane}for lane in range(3)]
    bank_path=root/'bank.json';bank_path.write_text(json.dumps(manifest));bank=load_bank(bank_path)
    data=clock_fixture();data['analysis_width']=200
    data['layout']['lanes']=[{'x':.1+i*.1}for i in range(3)]
    data['skin_detector']={'bank_path':str(bank_path),'contract':{'bank':bank['contract']},'registration_reviewed':False}
    data.pop('head_registration');frames={}
    for i,note in enumerate(data['notes']):
        note['points']=[(time,float(round(y)))for time,y in note['points']]
        for time,y in note['points']:
            frame=frames.setdefault(time,{'playback_seconds':time,'source_pts_seconds':80+time,'skin_observations':[]})
            frame['skin_observations'].append({'lane':note['lane'],'x':data['layout']['lanes'][note['lane']]['x'],
                'y':y/data['analysis_height'],'role':'tap','template':f'tap-{note["lane"]}',
                'classification_status':'full_pattern','skin':bank['skin'],'region_errors':{'cap':0.}})
    return data,list(frames.values())


class ImageCoordinateTest(unittest.TestCase):
    def test_same_positive_cap_pixels_supply_their_own_center_across_different_matching_origins(self):
        import numpy as np
        from tests.play.skins.test_anchor_registration import fixture as source_fixture,register
        from piu_timeline.play.skins.detector import SkinDetector
        from piu_timeline.play.skins.replay import detector_metadata
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);rgb,data,_=source_fixture(root);path=register(root,rgb)
            document=json.loads(path.read_text());start=next(t for t in document['templates']if t['id']=='hold_start')
            start.pop('native_anchor_registration');start['anchor_pixels'][1]+=1
            path.write_text(json.dumps(document));bank=load_bank(path)
            canvas=np.zeros_like(rgb)
            canvas[30:65,10:30]=rgb[60:95,10:30]
            canvas[100:135,10:30]=rgb[60:95,10:30]
            layout={'receptor_y':.05,'note_y_max':.95,'lanes':[{'x':.1+i*.1}for i in range(5)]}
            images=SkinDetector(bank,layout,200,160).detect(canvas)
            caps=[o for o in images if o['role']!='hold_body'and o['lane']==0]
            image=min(caps,key=lambda o:o['y']);self.assertEqual(image['role'],'hold_start')
            self.assertAlmostEqual(image['y']*160,41)
            data.update(layout=layout,notes=[{'lane':0,'points':[[2.,41.]]}],skin_detector=detector_metadata(path))
            frames=[{'playback_seconds':2.,'source_pts_seconds':5.,'skin_observations':images}]
            record=measure(data,frames)['notes'][0];sample=record['observations'][0]
            self.assertEqual(record['coordinate_status'],'projected')
            self.assertAlmostEqual(sample['native_y_pixels'],40)
            self.assertGreaterEqual(sample['native_cap_shared_pixel_evidence']['primary_fraction'],.8)
            self.assertGreaterEqual(sample['native_cap_shared_pixel_evidence']['reference_fraction'],.8)
            # Tracking consumes the measured view while retaining each raw origin.
            from piu_timeline.play.tracking import NoteTracker
            tracker=NoteTracker(layout,200,160,skin_bank=bank)
            detector=SkinDetector(bank,layout,200,160)
            for index in range(4):
                moving=np.zeros_like(canvas)
                for top in(30,100):
                    patch=rgb[60:95,10:30].copy()
                    if index%2:patch[20:,6:14]=[35,160,230]
                    moving[top-4*index:top-4*index+35,10:30]=patch
                observed=[o for o in detector.detect(moving)if o['role']!='hold_body']
                tracker.update(2+index*.025,observed,5+index*.025)
            self.assertEqual(len(tracker.active),2)
            first=min(tracker.active,key=lambda t:t.points[0][1])
            self.assertEqual(len(first.points),4)
            self.assertAlmostEqual(first.points[0][1],41)
            self.assertAlmostEqual(first.points[1][1],36)
            self.assertEqual([o['center']['yPixels']for o in first.tracking_observations],[40,36,32,28])
            # Shared comparison pixels also preserve identity without claiming
            # a native center when none of the references has a certificate.
            for entry in document['templates']:entry.pop('native_anchor_registration',None)
            unknown=root/'unregistered.json';unknown.write_text(json.dumps(document))
            unknown_bank=load_bank(unknown);uncalibrated=NoteTracker(layout,200,160,skin_bank=unknown_bank)
            for index in range(4):
                moving=np.zeros_like(canvas)
                for top in(30,100):
                    patch=rgb[60:95,10:30].copy()
                    if index%2:patch[20:,6:14]=[35,160,230]
                    moving[top-4*index:top-4*index+35,10:30]=patch
                observed=uncalibrated.detect(moving);uncalibrated.update(2+index*.025,observed,5+index*.025)
            self.assertEqual(len(uncalibrated.active),2)
            self.assertTrue(all(len(t.points)==4 for t in uncalibrated.active))
            self.assertTrue(all(o['center']is None for t in uncalibrated.active for o in t.tracking_observations))
            # A genuine positive match of the other glyph cannot calibrate this one.
            other=max(caps,key=lambda o:o['y'])
            alternative=next(p for p in other['alternatives']if p['template']in bank['anchor_registrations'])
            image['alternatives']=[alternative]
            sample=measure(data,frames)['notes'][0]['observations'][0]
            self.assertNotIn('native_cap_coordinate_uncertainty_pixels',sample)

    def test_unregistered_image_origins_fail_spacing_without_inventing_calibration(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);data,frames=fixture(root);original=deepcopy((data,frames))
            (root/'frames.jsonl').write_text(''.join(json.dumps(f)+'\n'for f in frames))
            with patch('piu_timeline.play.appearance.acquire',side_effect=AssertionError('No pixel reacquisition')):
                measured=apply(data,root)
            registration=measured['head_registration']
            self.assertEqual(registration['absolute_registration'],'unverified')
            self.assertEqual(len(registration['notes']),9)
            self.assertTrue(all(r['status']=='measured'and 'coordinate_uncertainty_pixels'not in r for r in registration['notes']))
            self.assertTrue(any(w['peer_notes']==[4,5]for w in spacing_failures(data['notes'],20,data['scroll_motion'])))
            checks=[];support=prepare(measured,20)
            failures=spacing_failures(data['notes'],20,data['scroll_motion'],support,checks)
            self.assertTrue(failures)
            self.assertTrue(all(w['failure_detail']=='incompatible_coordinate_origins'for w in failures))
            self.assertTrue(all(not heads for heads in support['chunks'].values()))
            self.assertFalse(any('models'in check for check in checks))
            self.assertEqual((data,frames),original)
            self.assertFalse(measured['skin_detector']['registration_reviewed'])
            self.assertEqual(json.loads((root/'head-registration.json').read_text()),registration)

    def test_context_variants_share_chord_geometry_only_with_identical_cap_sampling(self):
        from tests.play.skins.coordinate_fixtures import chord_fixture
        from piu_timeline.play.beats.chords import prepare as chords
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);data,frames=fixture(root);bank=load_bank(root/'bank.json')
            base=bank['templates'][0];context=deepcopy(base);context['id']='short-context'
            context['regions'][1]['box']=[6,6,14,8]
            identity=cap_reference(bank,base)
            self.assertEqual(measure(data,frames)['notes'][0]['observations'][0]['cap_reference_sha256'],identity)
            joint=chord_fixture();joint['layout']['lanes']=[{'x':.05+.1*i}for i in range(10)]
            for i,(note,record)in enumerate(zip(joint['notes'],joint['head_registration']['notes'])):
                note['lane']=(0,5,6)[i];record.update(status='measured',coordinate_method='native_image_anchors')
                record.pop('coordinate_uncertainty_pixels')
                for sample,(time,y)in zip(record['observations'],note['points'],strict=True):
                    sample.update(native_y_pixels=y,template='base'if i==0 else'short-context',
                                  cap_reference_sha256=identity if i==0 else cap_reference(bank,context)if i==1
                                  else cap_reference(bank,bank['templates'][1]))
            proofs=chords(joint,40)
            self.assertEqual(len(proofs),1)
            self.assertEqual(proofs[0]['reference_templates'],['base','short-context'])
            for change in ('anchor','pixels','mask'):
                different=deepcopy(context)
                if change=='anchor':different['anchor_pixels'][1]+=1
                elif change=='pixels':different['rgb'][0,0,0]^=1
                else:different['mask'][0,0]=not different['mask'][0,0]
                changed=deepcopy(joint)
                for sample in changed['head_registration']['notes'][1]['observations']:
                    sample['cap_reference_sha256']=cap_reference(bank,different)
                self.assertEqual(chords(changed,40),[],change)

    def test_missing_ambiguous_or_failed_cap_provenance_and_changed_bank_fail_explicitly(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);data,frames=fixture(root)
            for case in ('missing_frame','missing_cap','ambiguous_cap','bad_score','negative_score','wrong_kind','wrong_pts','changed_bank'):
                d,native=deepcopy(data),deepcopy(frames)
                image=native[0]['skin_observations'][0]
                if case=='missing_frame':native.pop(0)
                elif case=='missing_cap':native[0]['skin_observations'].pop(0)
                elif case=='ambiguous_cap':native[0]['skin_observations'].append(deepcopy(image))
                elif case=='bad_score':image['region_errors']['cap']=1.
                elif case=='negative_score':image['region_errors']['cap']=-1.
                elif case=='wrong_kind':image['template']='tap-1'
                elif case=='wrong_pts':native[0]['source_pts_seconds']+=.001
                else:d['skin_detector']['contract']['bank']={}
                with self.subTest(case=case),self.assertRaises(ValueError):measure(d,native)
