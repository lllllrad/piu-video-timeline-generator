from copy import deepcopy
import unittest

from piu_timeline.play_recovery import recover_rows


def evidence():
    return {'notes': [{'status': 'estimated', 'lane': 0, 'target_seconds': 1, 'prediction_uncertainty_seconds': .01}],
            'matches': [], 'combo_events': [{'delta': 1, 'lower_seconds': 1.02, 'upper_seconds': 1.04}],
            'judgment_events': [{'label': 'GREAT', 'delta': 1, 'lower_seconds': 1.02, 'upper_seconds': 1.04}],
            'hold_analysis': {'holds': [], 'receptor_runs': [
                {'lane': 0, 'lit': False, 'start_seconds': .9, 'end_seconds': 1, 'frames': 7},
                {'lane': 0, 'lit': True, 'start_seconds': 1.02, 'end_seconds': 1.08, 'frames': 4,
                 'onset_range': [1, 1.02], 'onset_source_pts_seconds': [11, 11.02]}]}}


class RowRecoveryTest(unittest.TestCase):
    def test_unique_row_uses_own_lane_and_original_bracket(self):
        data = evidence(); original = deepcopy(data)
        matches, recovered = recover_rows(data)
        self.assertEqual(data, original)
        self.assertEqual(recovered, [0])
        self.assertEqual(matches[0]['observation_lower_seconds'], 1.02)
        self.assertEqual(matches[0]['observation_upper_seconds'], 1.04)
        self.assertEqual(matches[0]['judgment_label'], 'GREAT')
        self.assertEqual(matches[0]['lane_onset_source_pts_seconds'], [11, 11.02])
        self.assertEqual(matches[0]['combo_event'], 0)

    def test_repeated_same_lane_rows_cannot_claim_one_onset(self):
        data = evidence()
        data['notes'].append({**data['notes'][0], 'target_seconds': 1.035})
        self.assertEqual(recover_rows(data)[1], [])
        data['matches'] = [{'note': 1, 'target_seconds': 1.035, 'combo_event': 0,
                            'observation_lower_seconds': 1.02, 'observation_upper_seconds': 1.04}]
        self.assertEqual(recover_rows(data)[1], [])

    def test_chord_shares_one_row_but_requires_both_lane_onsets(self):
        data = evidence()
        data['notes'].append({**data['notes'][0], 'lane': 1})
        data['hold_analysis']['receptor_runs'].extend([{**run, 'lane': 1} for run in data['hold_analysis']['receptor_runs']])
        matches, recovered = recover_rows(data)
        self.assertEqual(set(recovered), {0, 1})
        self.assertTrue(all(match['row_note_count'] == 2 for match in matches))
        data['hold_analysis']['receptor_runs'] = data['hold_analysis']['receptor_runs'][:2]
        self.assertEqual(recover_rows(data)[1], [0])

    def test_static_light_unknown_onset_single_frame_miss_and_gap_stay_unresolved(self):
        variants = []
        for change in ('static', 'single', 'missing', 'miss', 'gap', 'hold', 'distant'):
            data = evidence()
            run = data['hold_analysis']['receptor_runs'][1]
            if change == 'static':run['onset_range'] = None
            if change == 'single':run['frames'] = 1
            if change == 'missing':run['lane'] = 1
            if change == 'miss':
                data['combo_events'] = []; data['judgment_events'][0]['label'] = 'MISS'
            if change == 'gap':
                data['combo_events'][0]['lower_seconds'] = .5; data['judgment_events'][0]['lower_seconds'] = .5
            if change == 'hold':data['notes'][0]['note_type'] = 'hold'
            if change == 'distant':data['notes'][0]['target_seconds'] = .5
            variants.append((change, data))
        for change, data in variants:
            with self.subTest(change=change):
                self.assertEqual(recover_rows(data)[1], [])

    def test_conflicting_display_alternatives_remain_unresolved(self):
        data = evidence()
        data['combo_events'].append({'delta': 1, 'lower_seconds': 1.055, 'upper_seconds': 1.065})
        self.assertEqual(recover_rows(data)[1], [])
