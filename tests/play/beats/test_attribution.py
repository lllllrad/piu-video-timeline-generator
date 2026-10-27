"""A contradictory row cannot erase its independently verified neighbors."""
from copy import deepcopy
import unittest

from piu_timeline.play.beats.coordinates import prepare
from piu_timeline.play.spacing_checks import attributed_heads,spacing_failures
from tests.play.beats.test_coordinates import fixture


class SpacingAttributionTest(unittest.TestCase):
    def test_one_wrong_beat_row_rejects_only_that_head_with_original_native_proof(self):
        data=fixture();data['notes'][4]['target_seconds']+=.06
        original=deepcopy(data);support=prepare(data,40)
        failures=spacing_failures(data['notes'],40,data['scroll_motion'],support)
        self.assertEqual({w['note']for w in failures},{4})
        pair=next(w for w in failures if w['peer_notes']==[4,5])
        proof=pair['native_position_attribution'][0]
        self.assertEqual(proof['contradicting_notes'],[4])
        self.assertGreater(abs(proof['peer_position_errors_pixels'][0]),proof['maximum_position_error_pixels'])
        self.assertLessEqual(abs(proof['peer_position_errors_pixels'][1]),proof['maximum_position_error_pixels'])
        model=pair['independent_coordinate_models'][0]
        self.assertTrue({4,5}.isdisjoint(r['note']for r in model['references']))
        self.assertEqual(model['references'][0]['source_pts_range'],[80.5,80.68])
        self.assertEqual(data,original)

    def test_unattributed_or_contradictory_models_keep_both_heads_unresolved(self):
        notes=[{'target_seconds':0},{'target_seconds':1}]
        def model(offsets,chunk=0):
            return {'chunk':chunk,'peer_offsets_pixels':offsets,'maximum_reference_error_pixels':0,
                    'offset_at_origin_pixels':0,'origin_seconds':0,'velocity_pixels_per_second':10}
        for models in ([],[model([.75,9.25])],[model([0,13]),model([3,10],1)],[{}]):
            rejected,_=attributed_heads(0,1,notes,models)
            self.assertEqual(rejected,(0,1))

    def test_without_independent_coordinate_support_pair_conflicts_still_reject_both(self):
        data=fixture();data['notes'][4]['target_seconds']+=.06
        failures=spacing_failures(data['notes'],40,data['scroll_motion'])
        self.assertEqual({w['note']for w in failures if w['peer_notes']==[4,5]},{4,5})
