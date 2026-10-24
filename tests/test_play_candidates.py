import unittest

from piu_timeline.play_candidates import candidates


def note(time, lane=0):
    return {'status': 'estimated', 'target_seconds': time, 'prediction_uncertainty_seconds': .008, 'lane': lane}


def event(lo=10, hi=10.02, source='combo', index=0):
    return {'source': source, 'event': index, 'lower_seconds': lo, 'upper_seconds': hi, 'delta': 1}


def run(lane, lit, lo, hi, previous=None):
    return {'lane': lane, 'lit': lit, 'start_seconds': lo, 'end_seconds': hi,
            'previous_seconds': previous, 'frames': 10}


class CandidateTest(unittest.TestCase):
    def test_owned_refresh_cannot_also_be_a_later_note_or_duplicate_word_vote(self):
        data = {'notes': [note(10), note(10.08, 1)], 'matches': [
            {'note': 0, 'target_seconds': 10, 'combo_event': 0,
             'combo_lower_seconds': 10, 'combo_upper_seconds': 10.02}]}
        result, rejected = candidates(data, [event(), event(10.01, 10.03, 'judgment')])
        self.assertNotIn(1, result)
        self.assertIn('refresh_already_assigned_to_another_row', rejected[1])

    def test_owned_chord_can_add_a_supported_other_lane_head(self):
        data = {'notes': [note(10), note(10.005, 1)], 'matches': [
            {'note': 0, 'target_seconds': 10, 'combo_event': 0,
             'combo_lower_seconds': 10, 'combo_upper_seconds': 10.02}],
                'hold_analysis': {'receptor_runs': [run(1, False, 9, 9.98), run(1, True, 10, 10.1, 9.98)]}}
        result, _ = candidates(data, [event()])
        self.assertEqual(len(result[1]), 1)
        self.assertTrue(result[1][0]['lane_receptor_support'])

    def test_only_adjacent_lane_flashes_so_unlit_lane_is_rejected(self):
        data = {'notes': [note(10, 0), note(10, 1)], 'hold_analysis': {'receptor_runs': [
            run(0, False, 9, 9.98), run(0, True, 10, 10.1, 9.98),
            run(1, True, 8, 8.2, 7.9), run(1, False, 8.2, 11)]}}
        result, rejected = candidates(data, [event()])
        self.assertIn(0, result)
        self.assertNotIn(1, result)
        self.assertIn('receptor_lane_not_active', rejected[1])

    def test_nearby_before_and_after_rows_do_not_all_share_one_candidate(self):
        data = {'notes': [note(9.9), note(10), note(10.1)]}
        result, rejected = candidates(data, [event()])
        self.assertEqual(set(result), {1})
        self.assertIn('another_note_row_is_better_supported', rejected[0])
        self.assertIn('another_note_row_is_better_supported', rejected[2])

    def test_hold_ticks_require_a_separate_lane_onset_for_a_tap(self):
        data = {'notes': [note(10.5, 1)], 'hold_analysis': {
            'holds': [{'start_range': [10, 10.01], 'start_censored': False, 'end_range': [11, 11.01]}],
            'receptor_runs': [run(1, False, 9, 9.98), run(1, True, 10, 10.8, 9.98)]}}
        result, rejected = candidates(data, [event(10.5, 10.52, 'counter_frames')])
        self.assertFalse(result)
        self.assertIn('hold_tick_without_independent_lane_onset', rejected[0])
        data['hold_analysis']['receptor_runs'][1] = run(1, True, 10.49, 10.8, 10.48)
        result, _ = candidates(data, [event(10.5, 10.52, 'counter_frames')])
        self.assertIn(0, result)

    def test_real_frame_bracket_tie_retains_explicit_alternative_rows(self):
        data = {'notes': [note(9.995), note(10.025)]}
        result, _ = candidates(data, [event()])
        self.assertEqual(set(result), {0, 1})
        self.assertTrue(all(entries[0]['alternative_rows'] == 2 for entries in result.values()))

    def test_processed_row_order_rejects_earlier_note_after_a_later_anchor(self):
        data = {'notes': [note(10.1), note(9.99, 1), note(10.15, 1)], 'matches': [
            {'note': 0, 'target_seconds': 10.1, 'combo_event': 1,
             'combo_lower_seconds': 10.1, 'combo_upper_seconds': 10.12}]}
        result, rejected = candidates(data, [event(10.15, 10.17)])
        self.assertNotIn(1, result)
        self.assertIn('violates_processed_row_order', rejected[1])
        self.assertIn(2, result)

    def test_narrow_word_refresh_does_not_fan_out_over_aggregate_counter_rows(self):
        data = {'notes': [note(9.9), note(10)]}
        aggregate = {**event(9.89, 10.02), 'delta': 2}
        result, _ = candidates(data, [aggregate, event(10, 10.02, 'judgment')])
        self.assertEqual([entry['source'] for entry in result[0]], ['combo'])
        self.assertEqual({entry['source'] for entry in result[1]}, {'combo', 'judgment'})
