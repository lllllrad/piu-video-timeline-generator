"""A body-only reference update must not reacquire unchanged cap measurements."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.replay import detector_metadata,refresh
from piu_timeline.play.skins.reuse import reusable_groups
from tests.play.skins.test_detector import examples


class ImageReuseTest(unittest.TestCase):
    def test_body_update_matches_full_detection_and_annotation_changes_do_not_decode(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);old=root/'old';new=root/'new';old.mkdir();new.mkdir()
            items,_=examples(old);examples(new)
            tile=cv2.imread(str(new/'hold_body.png'),cv2.IMREAD_UNCHANGED);tile[:,:,:3]=[230,60,110]
            cv2.imwrite(str(new/'hold_body.png'),tile)
            source=root/'source.mkv';source.write_bytes(b'original media')
            layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1}for i in range(5)]}
            rgb=np.zeros((300,200,3),dtype='uint8');rgb[40:80,10:30]=items[0][1]
            rgb[180:192,16:24]=tile[:,:,:3][:,:,::-1]
            old_bank,new_bank=load_bank(old/'bank.json'),load_bank(new/'bank.json')
            previous=SkinDetector(old_bank,layout,200,300).detect(rgb)
            frames=[{'source_pts_seconds':31.,'playback_seconds':1.,'combo':42,
                     'notes':[o for o in previous if o['role']!='hold_body'],'skin_observations':previous,
                     'possible_hold_or_dense_stack':True}]
            trace=''.join(json.dumps(f)+'\n'for f in frames);(root/'frames.jsonl').write_text(trace)
            data={'media':{'path':str(source),'size_bytes':source.stat().st_size,'mtime_ns':source.stat().st_mtime_ns},
                  'skin_detector':detector_metadata(old/'bank.json'),'layout':layout,
                  'analysis_width':200,'analysis_height':300,'game_roi':[0,0,200,300],
                  'start_seconds':1.,'end_seconds':1.02,'frame_count':1}
            self.assertEqual(reusable_groups(data,new_bank),{'caps'})
            from piu_timeline.play.skins import replay
            original=replay.classified_frames
            def body_only(decoded,bank,*args):
                self.assertEqual({t['role']for t in bank['templates']},{'hold_body'})
                return original(decoded,bank,*args,jobs=1)
            with patch.object(replay,'decode_frames',return_value=iter([(31.,1.,rgb)])),patch.object(replay,'classified_frames',side_effect=body_only):
                data['skin_detector']=refresh(data,root,new/'bank.json')
            actual=json.loads((root/'frames.jsonl').read_text());expected=SkinDetector(new_bank,layout,200,300).detect(rgb)
            self.assertEqual(actual['skin_observations'],expected)
            self.assertEqual(actual['notes'],frames[0]['notes'])
            self.assertEqual(actual['combo'],42)
            self.assertFalse(actual['possible_hold_or_dense_stack'])
            manifest=json.loads((new/'bank.json').read_text());manifest['source_annotation']='reviewed pixels unchanged'
            (new/'bank.json').write_text(json.dumps(manifest))
            self.assertEqual(reusable_groups(data,load_bank(new/'bank.json')),set()) # old path changed; cannot prove old references
            # An immutable old bank proves that metadata-only changes need no RGB.
            reviewed=root/'reviewed';reviewed.mkdir();examples(reviewed)
            document=json.loads((old/'bank.json').read_text());document['source_annotation']='reviewed'
            (reviewed/'bank.json').write_text(json.dumps(document));data['skin_detector']=detector_metadata(old/'bank.json')
            (root/'frames.jsonl').write_text(trace)
            with patch.object(replay,'decode_frames',side_effect=AssertionError('Unchanged image acquisition must be reused')):
                refresh(data,root,reviewed/'bank.json')
            repeated=json.loads((root/'frames.jsonl').read_text())
            self.assertEqual(repeated['skin_observations'],previous)
            self.assertEqual(source.read_bytes(),b'original media')

    def test_missing_observations_and_corrupt_timestamps_fail_without_replacing_the_trace(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);examples(root);media=root/'source';media.write_bytes(b'original')
            data={'media':{'path':str(media),'size_bytes':media.stat().st_size,'mtime_ns':media.stat().st_mtime_ns},
                  'skin_detector':detector_metadata(root/'bank.json'),'analysis_width':200,'analysis_height':300,
                  'layout':{'receptor_y':.05,'lanes':[{'x':.1+i*.1}for i in range(5)]},'start_seconds':1.,'end_seconds':2.,'frame_count':2}
            native={'source_pts_seconds':31.,'playback_seconds':1.,'skin_observations':[],'notes':[]}
            for case in ('missing_images','duplicate_pts','nonfinite_pts'):
                first=deepcopy(native);second=deepcopy(native)
                if case=='missing_images':first.pop('skin_observations')
                elif case=='nonfinite_pts':first['source_pts_seconds']=float('nan')
                trace=json.dumps(first)+'\n'+json.dumps(second)+'\n';(root/'frames.jsonl').write_text(trace)
                with patch('piu_timeline.play.skins.replay.decode_frames',side_effect=AssertionError('No changed pixels')):
                    with self.assertRaises(ValueError):refresh(data,root,root/'bank.json')
                self.assertEqual((root/'frames.jsonl').read_text(),trace)

    def test_body_candidate_rules_invalidate_only_body_observations(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);examples(root);bank=load_bank(root/'bank.json')
            data={'skin_detector':deepcopy(detector_metadata(root/'bank.json'))}
            data['skin_detector']['contract']['detector'].pop('body_candidates')
            self.assertEqual(reusable_groups(data,bank),{'caps'})
            data['skin_detector']['contract']['detector']['horizontal_search_spacing']=.5
            self.assertEqual(reusable_groups(data,bank),set())

    def test_changed_rules_or_unverifiable_old_bank_cannot_authorize_reuse(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);examples(root);bank=load_bank(root/'bank.json')
            data={'skin_detector':detector_metadata(root/'bank.json')}
            self.assertEqual(reusable_groups(data,bank),{'caps','body'})
            interpretation=deepcopy(data);interpretation['skin_detector']['contract']['held_body']={}
            self.assertEqual(reusable_groups(interpretation,bank),{'caps','body'})
            changed=deepcopy(data);changed['skin_detector']['contract']['detector']={}
            self.assertEqual(reusable_groups(changed,bank),set())
            changed=deepcopy(data);changed['skin_detector']['contract']['bank']={}
            self.assertEqual(reusable_groups(changed,bank),set())
            (root/'bank.json').unlink()
            self.assertEqual(reusable_groups(data,bank),set())
