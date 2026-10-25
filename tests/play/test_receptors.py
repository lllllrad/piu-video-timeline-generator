import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from piu_timeline.play.receptors import fractions, observations, reject_common_flashes, onset_overlaps
from piu_timeline.play.holds.state import receptor_runs

LAYOUT={'receptor_y':.15,'lanes':[{'x':.38+.06*i} for i in range(5)]}


class ReceptorTest(unittest.TestCase):
    def test_flash_corroborates_single_observed_onset_without_filling_unknown_frames(self):
        samples = [(10, False, False), (10.02, True, False), (10.04, None, True),
                   (10.06, None, True), (10.08, True, False), (10.1, True, False)]
        def build(items):
            return [{'playback_seconds':time,'source_pts_seconds':time+100,
                     'receptor_lit':[lit],'common_receptor_flash':flash} for time,lit,flash in items]
        frames = build(samples); runs = receptor_runs(frames)
        first = runs[1]
        self.assertEqual(first['frames'], 1)
        self.assertEqual(first['end_seconds'], 10.02)
        self.assertTrue(onset_overlaps(first, 10.01, 10.03))
        self.assertEqual(first['corroborating_source_pts_seconds'], 110.08)
        self.assertIsNone(runs[-1]['onset_range'])
        self.assertFalse(onset_overlaps(runs[-1], 10, 10.2))
        self.assertEqual(frames[2]['receptor_lit'], [None])
        for changed in (samples[:2]+[(10.04,None,False)]+samples[3:],
                        samples[:4]+[(10.3,True,False),(10.32,True,False)]):
            self.assertFalse(onset_overlaps(receptor_runs(build(changed))[1], 10, 10.04))

    def test_short_shared_flash_preserves_a_bounded_lane_transition(self):
        frames = [{'playback_seconds':time,'source_pts_seconds':time+100,
                   'receptor_lit':[lit],'common_receptor_flash':lit is None}
                  for time,lit in [(10,False),(10.02,False),(10.04,None),(10.06,None),
                                   (10.08,True),(10.1,True)]]
        runs = receptor_runs(frames)
        onset = runs[-1]
        self.assertIsNone(onset['previous_lit'])
        self.assertEqual(onset['onset_range'],[10.02,10.08])
        self.assertEqual(onset['onset_source_pts_seconds'],[110.02,110.08])
        self.assertTrue(onset_overlaps(onset,10.04,10.06))
        self.assertFalse(onset_overlaps(onset,10.11,10.12))
        self.assertEqual(frames[2]['receptor_lit'],[None])

    def test_unknown_state_cannot_invent_an_onset_without_bounded_continuous_off_evidence(self):
        cases = [
            [(0,True,False),(.02,None,True),(.04,True,False),(.06,True,False)],
            [(0,None,True),(.02,True,False),(.04,True,False)],
            [(0,False,False),(.02,None,False),(.04,True,False),(.06,True,False)],
            [(0,False,False),(.02,None,True),(.2,True,False),(.22,True,False)],
            [(0,False,False)]+[(i*.02,None,True) for i in range(1,9)]+[(.18,True,False),(.2,True,False)],
        ]
        for samples in cases:
            with self.subTest(samples=samples):
                frames=[{'playback_seconds':time,'source_pts_seconds':time+100,
                         'receptor_lit':[lit],'common_receptor_flash':flash} for time,lit,flash in samples]
                onset=receptor_runs(frames)[-1]
                self.assertIsNone(onset['onset_range'])
                self.assertFalse(onset_overlaps(onset,0,.3))

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
            with patch('piu_timeline.play.receptors.decode_frames',return_value=iter(decoded)):
                first=observations(data,root,frames)
            with patch('piu_timeline.play.receptors.decode_frames',side_effect=AssertionError('cached')):
                self.assertTrue(np.array_equal(first,observations(data,root,frames)))
            saved=(root/'receptor-features.npz').read_bytes()
            with patch('piu_timeline.play.receptors.decode_frames',return_value=iter([(10.1,.1,decoded[0][2])])):
                with self.assertRaisesRegex(ValueError,'PTS differs'):
                    observations({**data,'end_seconds':1.1},root,frames)
            self.assertEqual((root/'receptor-features.npz').read_bytes(),saved)
            self.assertEqual(source.read_bytes(),b'original')
