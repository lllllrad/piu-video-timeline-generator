import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from piu_timeline.play_receptors import fractions, observations, reject_common_flashes
from piu_timeline.play_holds import receptor_runs

LAYOUT={'receptor_y':.15,'lanes':[{'x':.38+.06*i} for i in range(5)]}


class ReceptorTest(unittest.TestCase):
    def test_shared_flash_is_unknown_while_local_signal_survives_its_decay(self):
        frames=[{'playback_seconds':i*.02,'source_pts_seconds':i*.02+10,'receptor_lit':[True]*5}
                for i in range(6)]
        scores=np.array([[.1]*5,[.95]*5,[.9]*5,[.65,.65,1,.65,.65],
                         [.3,.3,1,.3,.3],[.1,.1,.98,.1,.1]])
        result=reject_common_flashes(frames,scores)
        self.assertEqual(result[1]['receptor_lit'],[None]*5)
        self.assertEqual(result[3]['receptor_lit'],[None,None,True,None,None])
        self.assertEqual(result[5]['receptor_lit'],[False,False,True,False,False])
        self.assertEqual(frames[1]['receptor_lit'],[True]*5)
        onset=next(run for run in receptor_runs(result) if run['lane']==2 and run['lit'] is True)
        self.assertIsNone(onset['previous_lit'])
        self.assertFalse(any(run['lit'] is True and run['lane']!=2 for run in receptor_runs(result)))

    def test_four_note_chord_is_not_confused_with_every_receptor_flashing(self):
        frame={'playback_seconds':1,'source_pts_seconds':11,'receptor_lit':[True]*4+[False]}
        self.assertEqual(reject_common_flashes([frame],np.array([[1,1,1,1,.1]]))[0]['receptor_lit'],frame['receptor_lit'])

    def test_strip_and_full_frame_measurements_are_identical(self):
        rgb=np.random.default_rng(1).integers(0,256,size=(183,325,3),dtype='uint8')
        # Receptor crop boundaries are y=21..31 for this geometry.
        self.assertEqual(fractions(rgb,LAYOUT),fractions(rgb[21:32],LAYOUT,183,21))

    def test_legacy_top_up_preserves_pts_and_then_reuses_independent_features(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source.mkv';source.write_bytes(b'original')
            data={'layout':LAYOUT,'media':{'path':str(source),'video_streams':[{'index':0}]},
                  'game_roi':[0,0,325,183],'start_seconds':0,'end_seconds':1}
            frames=[{'playback_seconds':0,'source_pts_seconds':10}]
            decoded=[(10,0,np.zeros((11,325,3),dtype='uint8'))]
            with patch('piu_timeline.play_receptors.decode_frames',return_value=iter(decoded)):
                first=observations(data,root,frames)
            with patch('piu_timeline.play_receptors.decode_frames',side_effect=AssertionError('cached')):
                self.assertTrue(np.array_equal(first,observations(data,root,frames)))
            saved=(root/'receptor-features.npz').read_bytes()
            with patch('piu_timeline.play_receptors.decode_frames',return_value=iter([(10.1,.1,decoded[0][2])])):
                with self.assertRaisesRegex(ValueError,'PTS differs'):
                    observations({**data,'end_seconds':1.1},root,frames)
            self.assertEqual((root/'receptor-features.npz').read_bytes(),saved)
            self.assertEqual(source.read_bytes(),b'original')
