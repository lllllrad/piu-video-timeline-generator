import unittest
from piu_timeline.tools.effect_capture import candidates
from piu_timeline.play.effect_images import select, augment


class EffectCaptureTest(unittest.TestCase):
    def test_full_play_includes_rebrightening_while_reference_sampling_does_not(self):
        rows = [{'playback_seconds': i/60, 'receptor_lit': [False], 'receptor_white_fraction': [0.]}
                for i in range(70)]
        for i in range(10, 70):
            rows[i].update(receptor_lit=[True], receptor_white_fraction=[.6])
        rows[30]['receptor_white_fraction'] = [.9]
        complete = candidates(rows)
        self.assertIn((10, 0, 'off_to_on_candidate'), complete)
        self.assertIn((30, 0, 'rebrightening_candidate'), complete)
        self.assertNotIn((30, 0, 'rebrightening_candidate'), candidates(rows, 12))

    def test_unknown_states_do_not_prove_off_to_on_and_empty_play_is_valid(self):
        rows = [{'playback_seconds': i/60, 'receptor_lit': [None], 'receptor_white_fraction': [.6]}
                for i in range(40)]
        self.assertFalse(any(c[2] == 'off_to_on_candidate' for c in candidates(rows)))
        self.assertEqual(candidates([]), [])

    def test_disabled_selection_clears_only_effect_interpretation(self):
        data = {'effect_reference': '/tmp/bank.json', 'effect_images': {},
                'notes': [{'target_seconds': 2, 'effect_image_candidates': ['one']}],
                'matches': [{'note': 0, 'raw_offset_ms': 12, 'effect_image_corroboration': ['one']}],
                'visual_channels': {'receptors': {'events': []}, 'effect_images': {}}}
        select(data, clear=True)
        self.assertIsNone(augment(data, None))
        self.assertEqual(data['notes'], [{'target_seconds': 2}])
        self.assertEqual(data['matches'], [{'note': 0, 'raw_offset_ms': 12}])
        self.assertEqual(data['visual_channels'], {'receptors': {'events': []}})
