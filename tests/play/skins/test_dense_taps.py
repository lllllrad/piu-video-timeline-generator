from types import SimpleNamespace
import unittest

import numpy as np

from piu_timeline.play.skins.dense_taps import proof


class DenseTapTest(unittest.TestCase):
    def test_exposed_pixels_must_refute_both_hold_roles(self):
        def template(role, rgb):
            return {'role': role, 'lane_kind': 0, 'anchor': [2,2],
                    'cap_support': np.ones((5,5), bool), 'rgb': np.full((5,5,3), rgb),
                    'regions': [{'name': 'cap', 'maximum_error': .015}]}

        tap = template('tap', 1.)
        start, end = template('hold_start', 0.), template('hold_end', .2)
        detector = SimpleNamespace(width=9, height=9, by_sampling={'tap': tap}, templates=[tap,start,end])
        head = {'role': 'unknown', 'lane': 0, 'template_role': 'tap', 'template': 'tap',
                'classification_status': 'cap_only', 'occlusion_evidence': True,
                'x': 4/9, 'y': 4/9, 'bounds_pixels': [2,2,7,7], 'region_errors': {'cap': 0.}}
        image = np.ones((9,9,3))
        hidden = np.zeros((9,9), bool)
        result = proof(detector, image, head, hidden)
        self.assertEqual(result['hold_variants_excluded'], {'hold_start': 9, 'hold_end': 9})
        self.assertGreaterEqual(result['minimum_distinguishing_pixels'], 12)

        hidden[2:7,2:6] = True
        self.assertIsNone(proof(detector, image, head, hidden))
        hidden.fill(False)
        end['rgb'][:] = 1.
        self.assertIsNone(proof(detector, image, head, hidden))
