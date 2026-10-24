import unittest
import numpy as np

from piu_timeline.chart_audio import align_features


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

    def test_mismatched_silent_and_repeated_music_are_unresolved(self):
        rng = np.random.default_rng(9)
        ref = rng.normal(size=(8, 2400))
        for obs in (rng.normal(size=(8, 3000)), np.zeros((8, 3000)), np.tile(ref, (1, 2))):
            with self.subTest(shape=obs.shape), self.assertRaisesRegex(ValueError, 'ambiguous'):
                align_features(ref, obs)
