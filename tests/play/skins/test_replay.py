"""Switching image detectors preserves source PTS and counter observations."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from piu_timeline.play.skins.replay import refresh, selected_bank
from tests.play.skins.test_detector import examples


class SkinReplayTest(unittest.TestCase):
    def test_replay_preserves_original_trace_and_every_counter_and_timestamp(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);bank=root/'bank';bank.mkdir();items,_=examples(bank)
            media=root/'source.mkv';media.write_bytes(b'unchanged source')
            image=np.zeros((300,200,3),dtype='uint8');image[50:70,10:30]=items[0][1]
            frames=[{'source_pts_seconds':t+30,'playback_seconds':t,'notes':[],
                     'combo':i+4,'combo_confidence':.95}for i,t in enumerate((1.,1.02))]
            trace=''.join(json.dumps(f)+'\n'for f in frames)
            (root/'frames.jsonl').write_text(trace)
            data={'media':{'path':str(media),'size_bytes':media.stat().st_size,'mtime_ns':media.stat().st_mtime_ns},
                  'analysis_width':200,'analysis_height':300,'game_roi':[0,0,200,300],
                  'start_seconds':1,'end_seconds':1.04,'frame_count':2,
                  'layout':{'receptor_y':.05,'lanes':[{'x':.1+i*.1,'color':'blue'}for i in range(5)]}}
            decoded=[(f['source_pts_seconds'],f['playback_seconds'],image)for f in frames]
            with patch('piu_timeline.play.skins.replay.decode_frames',return_value=iter(decoded)):
                metadata=refresh(data,root,bank/'bank.json')
            updated=[json.loads(line)for line in (root/'frames.jsonl').read_text().splitlines()]
            self.assertEqual((root/'frames.outline.jsonl').read_text(),trace)
            self.assertEqual((root/'frames.base.jsonl').read_text(),(root/'frames.jsonl').read_text())
            for old,new in zip(frames,updated,strict=True):
                self.assertEqual({k:new[k]for k in old if k!='notes'},{k:v for k,v in old.items()if k!='notes'})
                self.assertEqual(new['notes'][0]['role'],'tap')
            self.assertTrue(metadata['missing_template_roles'])
            before=(root/'frames.jsonl').read_bytes()
            with patch('piu_timeline.play.skins.replay.decode_frames',return_value=iter([(99.,1.,image)])),self.assertRaises(ValueError):
                refresh(data,root,bank/'bank.json')
            self.assertEqual((root/'frames.jsonl').read_bytes(),before)
            self.assertEqual(media.read_bytes(),b'unchanged source')

    def test_source_selection_is_explicit_and_duplicate_profiles_fail(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary)
            self.assertIsNone(selected_bank(root,1))
            profile={'segments':[1,3],'bank':'images/bank.json'}
            path=root/'note-skins.json';path.write_text(json.dumps({'schema':1,'profiles':[profile]}))
            self.assertEqual(selected_bank(root,3),str(root/'images/bank.json'))
            self.assertIsNone(selected_bank(root,4))
            path.write_text(json.dumps({'schema':1,'profiles':[profile,profile]}))
            with self.assertRaises(ValueError):selected_bank(root,1)
