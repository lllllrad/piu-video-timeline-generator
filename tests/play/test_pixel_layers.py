"""Synthetic ownership and cache boundaries between acquisition and interpretation."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from piu_timeline.play.holds.features import acquire_features, feature_contract
from piu_timeline.play.pixel_cache import source_contract
from piu_timeline.play.processing import observe_processing
from tests.play.test_visual_channels import pixel_play


class PixelLayerTest(unittest.TestCase):
    def test_chart_failure_does_not_erase_disappearance_or_restore_timing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data, _ = pixel_play(root)
            expected = observe_processing(data, root/'processing-features.npz')['notes'][0]
            for reason in ('shared_timing_reconstruction_failed', 'beat_timing_reconstruction_failed'):
                failed = deepcopy(data)
                failed['notes'][0].update(status='excluded', reason=reason, target_seconds=None,
                                         prediction_uncertainty_seconds=100,
                                         timing_reconstruction={'status':'failed'})
                before = deepcopy(failed)
                actual = observe_processing(failed, root/'processing-features.npz')['notes'][0]
                self.assertEqual(actual['status'], 'disappeared_near_receptor')
                self.assertEqual(actual['source_pts_seconds'], expected['source_pts_seconds'])
                self.assertEqual(actual['motion_basis'], 'bounded_native_trajectory')
                self.assertEqual(failed, before)
            # Nonlinear native motion cannot become evidence through a rejected target.
            failed['notes'][0]['points'] = [[i/60, 120+(i % 2)*30] for i in range(12)]
            self.assertEqual(observe_processing(failed, root/'processing-features.npz')['notes'][0]['status'], 'unresolved')

    def test_detector_revisions_reuse_masks_and_preserve_pixel_contracts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root/'source.mkv'; source.write_bytes(b'original source')
            layout = {'lanes':[{'x':.2+.1*i,'color':color} for i,color in enumerate(('blue','red','yellow','red','blue'))],
                      'receptor_y':.3,'note_y_max':.95}
            data = {'layout':layout,'media':{'path':str(source)},'start_seconds':0,'end_seconds':1,
                    'game_roi':[0,0,325,200]}
            image = np.zeros((200,325,3),dtype='uint8')
            cv2.rectangle(image,(123,100),(137,175),(255,255,0),-1)
            decoded = [(10+i/60,i/60,image) for i in range(130)]
            (root/'frames.jsonl').write_text(''.join(json.dumps({'source_pts_seconds':p,'playback_seconds':t})+'\n' for p,t,_ in decoded))
            with patch('piu_timeline.play.holds.features.decode_frames',return_value=iter(decoded)):
                acquire_features(data,root)
            before = (root/'processing-features.npz').read_bytes()
            observations = (root/'hold-frames.jsonl').read_bytes()
            first = json.loads(observations.splitlines()[0])
            self.assertTrue(any(b['lane'] == 2 and b['long'] for b in first['bodies']))
            self.assertEqual(len(list((root/'native-features').glob('*.npz'))),2)
            manifest = (root/'native-features/manifest.json').read_bytes()
            from piu_timeline.play.holds.features import FEATURE_FORMAT
            with patch.dict(FEATURE_FORMAT,detector_revision=999), \
                    patch('piu_timeline.play.holds.features.decode_frames',side_effect=AssertionError('must reuse masks')):
                acquire_features(data,root)
                self.assertEqual(json.loads((root/'hold-features.json').read_text())['contract'],feature_contract(data))
            self.assertEqual(manifest,(root/'native-features/manifest.json').read_bytes())
            self.assertEqual(observations,(root/'hold-frames.jsonl').read_bytes())
            with np.load(root/'processing-features.npz',allow_pickle=False) as saved:
                self.assertEqual(json.loads(str(saved['contract']))['source'],source_contract(data))
            self.assertTrue(before)
            self.assertEqual(source.read_bytes(),b'original source')
            # Cached PTS mismatch fails rather than joining different frames.
            (root/'hold-features.json').unlink()
            (root/'frames.jsonl').write_text(json.dumps({'source_pts_seconds':99,'playback_seconds':0})+'\n')
            with patch('piu_timeline.play.holds.features.decode_frames',side_effect=AssertionError('must reuse masks')):
                with self.assertRaisesRegex(ValueError,'source PTS'):
                    acquire_features(data,root)

    def test_popup_exposes_baseline_without_overwriting_contextual_read(self):
        from piu_timeline.play.channels import collect
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data, frames = pixel_play(root)
            for frame in frames:
                frame['combo_confidence'] = .5
            (root/'frames.base.jsonl').write_text(''.join(json.dumps(f)+'\n' for f in frames))
            current = deepcopy(frames)
            current[60].update(combo=4, combo_confidence=.95, combo_read_mode='contextual', combo_recovered=True)
            (root/'frames.jsonl').write_text(''.join(json.dumps(f)+'\n' for f in current))
            channels = collect(data, root, frames)
            values = dict(zip(channels['popup']['observation_fields'],channels['popup']['observations'][60], strict=True))
            self.assertEqual(values['combo'],4)
            self.assertIsNone(values['baseline_combo'])
            self.assertTrue(values['combo_recovered'])
            self.assertEqual(values['combo_read_mode'],'contextual')
            baseline = frames[:-1]
            (root/'frames.base.jsonl').write_text(''.join(json.dumps(f)+'\n' for f in baseline))
            with self.assertRaisesRegex(ValueError,'baseline differs'):
                collect(data,root,frames)
