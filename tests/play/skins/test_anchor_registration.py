"""Source pixels and independent cap measurements must agree before sharing anchors."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from piu_timeline.play.head_registration import FORMAT as MEASUREMENT_FORMAT
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.calibration import register_anchors
from piu_timeline.play.skins.reuse import reusable_groups
from piu_timeline.play.skins.replay import detector_metadata
from tests.play.skins.test_detector import examples


def fixture(root):
    items,manifest=examples(root);media=root/'source.bin';media.write_bytes(b'synthetic source identity')
    stat=media.stat();identity={'path':str(media),'size_bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns}
    rgb=np.zeros((160,200,3),dtype='uint8');notes=[];records=[]
    for i,((role,image,anchor,_),template,top)in enumerate(zip(items[:3],manifest['templates'][:3],(20,60,100))):
        height,width=image.shape[:2];crop=[10,top,10+width,top+height];center=top+anchor[1]
        rgb[top:top+height,10:10+width]=image
        template['source_evidence']={'media':identity,'roi':[0,0,200,160],'source_note':i,
            'reference_dimensions':[200,160],'source_pts_seconds':5.,'playback_seconds':2.,'source_crop':crop}
        sample={'time':2.,'source_pts_seconds':5.,'detected_y_pixels':center-1,'offset_pixels':1.}
        records.append({'note':i,'lane':0,'coordinate_method':'native_cap_measurements',
                        'coordinate_uncertainty_pixels':1.,'status':'measured_only','observations':[sample]})
        notes.append({'lane':0,'points':[[2.,center-1]]})
    registration={'format':MEASUREMENT_FORMAT,'trace':'appearance-features.npz','notes':records}
    data={'media':identity,'game_roi':[0,0,200,160],'analysis_width':200,'analysis_height':160,
          'layout':{'lanes':[{'x':.1+i*.1}for i in range(5)]},'notes':notes,'head_registration':registration}
    (root/'bank.json').write_text(json.dumps(manifest));(root/'analysis.json').write_text(json.dumps(data))
    (root/'head-registration.json').write_text(json.dumps(registration))
    return rgb,data,manifest


def register(root,rgb,name='registered'):
    with patch('piu_timeline.play.skins.calibration.decode_frames',return_value=iter([(5.,2.,rgb)])):
        return register_anchors(root/'bank.json',root/'analysis.json',root/'head-registration.json',root/name)


def chord_trace(path):
    from tests.play.skins.coordinate_fixtures import chord_fixture
    bank=load_bank(path);data=chord_fixture();data['analysis_width']=200
    data['layout']['lanes']=[{'x':.05+i*.1}for i in range(10)]
    data['notes']=data['notes'][:2];data.pop('head_registration')
    data['notes'][0]['lane']=0;data['notes'][1]['lane']=5
    # These consumer fixtures supply reference-space coordinates directly;
    # they do not claim the current RGB detector's acquisition contract.
    data['skin_detector']={'bank_path':str(path),'contract':{'bank':bank['contract']},
                           'registration_reviewed':False};frames=[]
    for time,y in data['notes'][0]['points']:
        frames.append({'playback_seconds':time,'source_pts_seconds':50+time,'skin_observations':[
            {'lane':lane,'x':data['layout']['lanes'][lane]['x'],'y':y/data['analysis_height'],
             'role':role,'template':role,'skin':bank['skin'],'classification_status':'full_pattern',
             'region_errors':{'cap':0.}}for lane,role in ((0,'tap'),(5,'hold_start'))]})
    return data,frames


class AnchorRegistrationTest(unittest.TestCase):
    def test_actual_pixels_and_native_centers_certify_only_caps_and_reuse_all_image_groups(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);rgb,_,_=fixture(root)
            original={n:sha256((root/n).read_bytes()).hexdigest()for n in ('bank.json','source.bin')}
            old=detector_metadata(root/'bank.json');path=register(root,rgb);bank=load_bank(path)
            self.assertEqual(set(bank['anchor_registrations']),{'tap','hold_start','hold_end'})
            self.assertFalse(detector_metadata(path)['registration_reviewed'])
            self.assertEqual(reusable_groups({'skin_detector':old},bank),{'caps/0','body/0'})
            proof=bank['templates'][0]['native_anchor_registration']
            self.assertEqual(proof['native_measurement']['source_pts_seconds'],5.)
            self.assertEqual(proof['native_measurement']['time'],2.)
            self.assertEqual(proof['source_frame_sha256'],sha256(rgb.tobytes()).hexdigest())
            report=json.loads((path.parent/'anchor-registration-report.json').read_text())
            self.assertEqual(report['decoded_reference_frames'],1)
            self.assertEqual(report['counts'],{'registered':3})
            self.assertEqual(original,{n:sha256((root/n).read_bytes()).hexdigest()for n in original})
            with self.assertRaises(FileExistsError):register(root,rgb)

    def test_wrong_pixels_and_missing_measurements_leave_specific_references_unregistered(self):
        for kind in ('wrong_pixels','missing_measurement'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory()as temporary:
                root=Path(temporary);rgb,data,_=fixture(root)
                if kind=='wrong_pixels':rgb[30,10,0]^=1
                else:
                    data['head_registration']['notes'][0]['observations']=[]
                    (root/'analysis.json').write_text(json.dumps(data))
                    (root/'head-registration.json').write_text(json.dumps(data['head_registration']))
                path=register(root,rgb);bank=load_bank(path)
                self.assertEqual(set(bank['anchor_registrations']),{'hold_start','hold_end'})
                report=json.loads((path.parent/'anchor-registration-report.json').read_text())
                self.assertEqual(next(r for r in report['templates']if r['template']=='tap')['status'],'unverified')

    def test_source_spacing_roundoff_requires_identical_native_image_dimensions(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);rgb,data,manifest=fixture(root)
            manifest['spacing_pixels']=20.00025
            (root/'bank.json').write_text(json.dumps(manifest))
            self.assertEqual(len(load_bank(register(root,rgb))['anchor_registrations']),3)
            data['layout']['lanes']=[{'x':.05+i*.2}for i in range(5)]
            (root/'analysis.json').write_text(json.dumps(data))
            with self.assertRaises(ValueError):register(root,rgb,'wrong-scale')
            self.assertFalse((root/'wrong-scale').exists())

    def test_changed_pixels_masks_anchor_source_or_measurement_cannot_reuse_a_certificate(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);rgb,_,_=fixture(root);path=register(root,rgb)
            original=json.loads(path.read_text());image_path=path.parent/'tap.png';pixels=cv2.imread(str(image_path),cv2.IMREAD_UNCHANGED)
            for kind in ('pixels','mask','anchor','source','measurement','crop'):
                changed=deepcopy(original);image=pixels.copy();entry=changed['templates'][0]
                if kind=='pixels':image[10,0,0]^=1
                elif kind=='mask':image[10,0,3]=0
                elif kind=='anchor':entry['anchor_pixels'][1]+=.5
                elif kind=='source':entry['source_evidence']['source_pts_seconds']+=.01
                elif kind=='measurement':entry['native_anchor_registration']['native_measurement']['offset_pixels']+=.5
                else:entry['native_anchor_registration']['source_crop'][1]+=1
                path.write_text(json.dumps(changed));cv2.imwrite(str(image_path),image)
                with self.subTest(kind=kind),self.assertRaises(ValueError):load_bank(path)

    def test_registered_reference_coordinates_enable_cross_template_chords_without_absolute_calibration(self):
        from piu_timeline.play.beats.chords import prepare
        from piu_timeline.play.skins.coordinates import measure
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);rgb,_,_=fixture(root);path=register(root,rgb)
            data,frames=chord_trace(path)
            data['head_registration']=measure(data,frames)
            self.assertEqual(data['head_registration']['absolute_registration'],'unverified')
            proofs=prepare(data,40)
            self.assertEqual(len(proofs),1)
            self.assertEqual(proofs[0]['measurement_basis'],'source_bound_native_cap_centers')
            self.assertEqual(proofs[0]['registered_image_templates'],['hold_start','tap'])
            enlarged=deepcopy(data);enlarged['analysis_width']=400
            enlarged['head_registration']=measure(enlarged,frames)
            self.assertEqual(enlarged['head_registration']['notes'][0]['observations'][0]['native_cap_coordinate_uncertainty_pixels'],2.)
            self.assertEqual(prepare(enlarged,40),[])
            smaller=deepcopy(data);smaller['analysis_width']=100
            smaller['head_registration']=measure(smaller,frames)
            self.assertEqual(smaller['head_registration']['notes'][0]['observations'][0]['native_cap_coordinate_uncertainty_pixels'],.5)
            for record in data['head_registration']['notes']:
                for sample in record['observations']:
                    sample.pop('native_cap_coordinate_uncertainty_pixels');sample.pop('native_cap_reference_scale_y')
            # Without source registration, these distinct references cannot be pooled.
            self.assertEqual(prepare(data,40),[])
            sample=data['head_registration']['notes'][0]['observations'][0]
            sample['native_cap_coordinate_uncertainty_pixels']=.1
            sample['native_cap_reference_scale_y']=1.
            with self.assertRaises(ValueError):prepare(data,40)

    def test_coincident_registered_alternative_supplies_its_own_coordinate_proof(self):
        from piu_timeline.play.beats.chords import prepare
        from piu_timeline.play.skins.coordinates import measure
        from piu_timeline.play.exclusions import recognition_diagnostics
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);rgb,_,_=fixture(root);path=register(root,rgb)
            document=json.loads(path.read_text())
            next(t for t in document['templates']if t['id']=='hold_start').pop('native_anchor_registration')
            path.write_text(json.dumps(document));data,frames=chord_trace(path)
            for frame in frames:
                image=frame['skin_observations'][1]
                alternative={**image,'template':'tap','role':'unknown','classification_status':'cap_only',
                             'region_errors':{'cap':.0001}}
                image['alternatives']=[alternative]
            original=deepcopy(frames);data['head_registration']=measure(data,frames)
            sample=data['head_registration']['notes'][1]['observations'][0]
            self.assertEqual(sample['template'],'hold_start')
            self.assertEqual(sample['native_cap_reference_template'],'tap')
            self.assertEqual(sample['native_cap_comparison_index'],1)
            self.assertEqual(sample['native_cap_reference_error'],.0001)
            self.assertEqual(prepare(data,40)[0]['registered_image_templates'],['tap'])
            self.assertEqual(data['head_registration']['warnings'],[])
            self.assertEqual(frames,original)
            for case in ('failed_cap','different_row','conflicting_row','registered_primary_conflict'):
                changed=deepcopy(original)
                for frame in changed:
                    image=frame['skin_observations'][1];alt=image['alternatives'][0]
                    if case=='failed_cap':alt['region_errors']['cap']=.1
                    elif case=='different_row':alt['y']+=.5/data['analysis_height']
                    elif case=='conflicting_row':
                        image['alternatives'].append({**alt,'template':'hold_end','y':alt['y']+3/data['analysis_height']})
                    else:
                        first=frame['skin_observations'][0]
                        first['alternatives']=[{**first,'template':'hold_end','y':first['y']+3/data['analysis_height']}]
                actual=measure(data,changed);index=0 if case=='registered_primary_conflict'else 1
                measured=actual['notes'][index]['observations'][0]
                with self.subTest(case=case):
                    self.assertNotIn('native_cap_coordinate_uncertainty_pixels',measured)
                    self.assertEqual(prepare({**data,'head_registration':actual},40),[])
                    if 'conflict'in case:
                        self.assertEqual(actual['status'],'failed')
                        self.assertEqual(measured['native_cap_registration_status'],'conflicting')
                        warning=actual['warnings'][0]
                        self.assertEqual(warning['note'],index)
                        self.assertEqual(warning['observed_points'],9)
                        self.assertEqual(warning['source_pts_seconds'][0],50.6)
                        reviewed={**data,'head_registration':actual,'start_seconds':.5,'end_seconds':1.2}
                        warnings=recognition_diagnostics(reviewed,{'notes':{}})['warnings']
                        self.assertTrue(any(w['reason']=='conflicting_registered_image_anchors'for w in warnings))
                    else:self.assertEqual(actual['warnings'],[])

    def test_mismatched_source_artifact_or_media_fails_before_creating_a_bank(self):
        for kind in ('artifact','media'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory()as temporary:
                root=Path(temporary);rgb,data,_=fixture(root)
                if kind=='artifact':
                    data['head_registration']['notes'][0]['observations'][0]['offset_pixels']+=.5
                    (root/'head-registration.json').write_text(json.dumps(data['head_registration']))
                else:(root/'source.bin').write_bytes(b'changed recording identity')
                with self.assertRaises(ValueError):register(root,rgb)
                self.assertFalse((root/'registered').exists())
