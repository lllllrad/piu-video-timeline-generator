from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np

from piu_timeline.charts.audio import align, align_features


class AudioAlignmentTest(unittest.TestCase):
    def test_music_with_independent_noise_recovers_translation(self):
        rng = np.random.default_rng(42)
        ref = rng.normal(size=(8, 2400))
        obs = rng.normal(size=(8, 3000)) * .25
        obs[:, 137:2537] += ref
        result = align_features(ref, obs)
        self.assertAlmostEqual(result['offset_seconds'], 1.37)
        self.assertEqual(result['accepted_windows'], 3)
        self.assertEqual(result['rate'], 1)

    def test_excerpt_windows_find_a_late_translation_in_the_full_reference(self):
        rng = np.random.default_rng(76)
        reference = rng.normal(size=(8, 9000))
        excerpt = reference[:, 4700:7500] + rng.normal(size=(8, 2800)) * .1
        with TemporaryDirectory() as directory:
            source = Path(directory)/'play.mkv'
            source.touch()
            stat = source.stat()
            data = {'start_seconds': 123.0, 'end_seconds': 151.0,
                    'media': {'path': str(source), 'size_bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}}
            with patch('piu_timeline.charts.audio.features', side_effect=[reference, excerpt]):
                result = align(data, Path(directory)/'official.mp3', excerpt=True)
        self.assertAlmostEqual(result['song_start_seconds'], 76.0)
        self.assertEqual(result['accepted_windows'], 3)
        self.assertTrue(all('excerpt_start_seconds' in window for window in result['windows']))

    def test_mismatched_silent_and_repeated_music_are_unresolved(self):
        rng = np.random.default_rng(9)
        ref = rng.normal(size=(8, 2400))
        for obs in (rng.normal(size=(8, 3000)), np.zeros((8, 3000)), np.tile(ref, (1, 2))):
            with self.subTest(shape=obs.shape), self.assertRaisesRegex(ValueError, 'ambiguous'):
                align_features(ref, obs)
