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
