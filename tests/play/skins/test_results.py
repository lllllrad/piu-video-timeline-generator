"""Stage results retain decisions while isolating image comparison searches."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from piu_timeline.play.observations.skin_results import publish, restore
from piu_timeline.play.observations.trace import stream_frames
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.frame_centers import FrameCenters
from tests.play.skins.test_detector import examples


class ResolvedFrameTests(unittest.TestCase):
    def prepare(self, root):
        items, _ = examples(root)
        bank = load_bank(root/'bank.json')
        layout = {'receptor_y': .05, 'lanes': [{'x': .1+i*.1} for i in range(5)]}
        detector = SkinDetector(bank, layout, 200, 300)
        rgb = np.zeros((300, 200, 3), dtype='uint8')
        rgb[40:80, 10:30] = items[0][1]
        images = detector.detect(rgb)
        frame = {'source_pts_seconds': 31., 'playback_seconds': 1., 'combo': 42,
                 'notes': [o for o in images if o['role'] != 'hold_body'],
                 'skin_observations': images, 'possible_hold_or_dense_stack': False}
        return frame, FrameCenters(detector)

    def test_tracking_reads_results_without_search_or_archive_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frame, centers = self.prepare(root)
            original = deepcopy(frame)
            expected = centers.positions(frame['notes'])
            compact = publish(frame, root, centers)
            self.assertEqual(restore(compact, root)['skin_observations'], frame['skin_observations'])
            self.assertEqual(frame, original)
            self.assertTrue(all('alternatives' not in image for image in compact['skin_observations']))
            path = root/'frames.jsonl'
            path.write_text(json.dumps(compact)+'\n')
            with patch.object(centers, 'prepare', side_effect=AssertionError('No image search in tracking')):
                with stream_frames(path, 1) as frames:
                    self.assertEqual(centers.positions(next(frames)['notes']), expected)
            with stream_frames(path, 1, comparisons=True) as frames:
                self.assertEqual(next(frames)['skin_observations'], frame['skin_observations'])
            compact['notes'][0]['position_contract'] = {'foreign': True}
            with self.assertRaisesRegex(ValueError, 'another bank'):
                centers.positions(compact['notes'])

    def test_native_remeasurement_rejects_corrupt_or_foreign_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frame, centers = self.prepare(root)
            compact = publish(frame, root, centers)
            foreign = {**compact, 'source_pts_seconds': 99.}
            with self.assertRaisesRegex(ValueError, 'another native frame'):
                restore(foreign, root)
            foreign = {**compact, 'comparison_evidence': {'path': '../outside.gz'}}
            with self.assertRaisesRegex(ValueError, 'within the play'):
                restore(foreign, root)
            compact['comparison_evidence']['sha256'] = 'wrong'
            with self.assertRaisesRegex(ValueError, 'Corrupt'):
                restore(compact, root)
