"""Independent row recovery must preserve strict popup ownership."""
from copy import deepcopy
import unittest

from piu_timeline.play.recovered_judgments import attach_recovered_labels


class RecoveredJudgmentsTest(unittest.TestCase):
    def data(self):
        return {'combo_events': [{'delta': 1, 'status': 'excluded',
                                 'reason': 'possible_hold_or_dense_stack',
                                 'lower_seconds': 1., 'upper_seconds': 1.017}],
                'judgment_events': [{'label': 'PERFECT', 'status': 'excluded',
                                     'reason': 'possible_hold_or_dense_stack',
                                     'detection_status': 'candidate', 'trigger': 'animation_restart',
                                     'lower_seconds': 1., 'upper_seconds': 1.017}],
                'matches': [{'note': 0, 'combo_event': 0, 'target_seconds': 1.01,
                             'aggregate_row_count': 1, 'evidence_source': 'combo+lane_onset',
                             'recovery_method': 'strict_row_alignment_with_independent_lane_evidence',
                             'observation_lower_seconds': 1., 'observation_upper_seconds': 1.017}]}

    def test_unique_refresh_labels_recovered_chord_without_changing_input(self):
        data = self.data()
        data['matches'].append({**data['matches'][0], 'note': 1})
        before = deepcopy(data)
        result = attach_recovered_labels(data)
        self.assertEqual(data, before)
        self.assertEqual([m['judgment_label'] for m in result['matches']], ['PERFECT']*2)
        self.assertEqual(result['judgment_events'][0]['anchor_combo_event'], 0)
        for original, match in zip(before['matches'], result['matches'], strict=True):
            self.assertEqual({key: match[key] for key in original if key != 'evidence_source'},
                             {key: value for key, value in original.items() if key != 'evidence_source'})
            self.assertEqual(match['evidence_source'], 'combo+lane_onset+judgment')
            self.assertEqual(match['judgment_label_source'], 'recovered_synchronized_refresh')
        self.assertEqual(attach_recovered_labels(result), result)

    def test_competing_native_word_or_counter_keeps_label_unknown(self):
        for key in ('judgment_events', 'combo_events'):
            with self.subTest(channel=key):
                data = self.data()
                other = {**data[key][0], 'status': 'candidate' if key == 'judgment_events' else 'excluded'}
                if key == 'combo_events':
                    other['reason'] = 'ambiguous_note_or_combo_association'
                data[key].append(other)
                self.assertNotIn('judgment_label', attach_recovered_labels(data)['matches'][0])

    def test_owned_refresh_cannot_be_stolen(self):
        data = self.data()
        data['matches'].append({'note': 1, 'combo_event': None, 'judgment_event': 0,
                                'judgment_label': 'PERFECT', 'target_seconds': 1.04})
        self.assertNotIn('judgment_label', attach_recovered_labels(data)['matches'][0])

    def test_unproven_row_aggregate_separated_rows_miss_and_invalid_detection_are_rejected(self):
        for case in ('unproven', 'aggregate', 'separated', 'miss', 'invalid', 'anchor'):
            with self.subTest(case=case):
                data = self.data()
                if case == 'unproven':
                    data['matches'][0].pop('recovery_method')
                elif case == 'aggregate':
                    data['combo_events'][0]['delta'] = 2
                elif case == 'separated':
                    data['matches'].append({**data['matches'][0], 'note': 1, 'target_seconds': 1.1})
                elif case == 'miss':
                    data['judgment_events'][0]['label'] = 'MISS'
                elif case == 'invalid':
                    data['judgment_events'][0]['detection_status'] = 'excluded'
                else:
                    data['judgment_events'][0]['anchor_combo_event'] = 1
                self.assertNotIn('judgment_label', attach_recovered_labels(data)['matches'][0])

    def test_persistent_label_without_observed_refresh_remains_unknown(self):
        data = self.data()
        data['judgment_events'] = []
        self.assertNotIn('judgment_label', attach_recovered_labels(data)['matches'][0])

    def test_presentation_reconnects_only_after_independent_lane_recovery(self):
        from piu_timeline.play.holds.analysis import presentation
        data = self.data()
        deferred = data['matches'].pop()
        deferred.update(combo_lower_seconds=1., combo_upper_seconds=1.017)
        data.update(notes=[{'lane': 0, 'status': 'estimated', 'target_seconds': 1.01}],
                    deferred_matches=[deferred], hold_analysis={'holds': [], 'receptor_runs': []})
        self.assertEqual(presentation(data)['matches'], [])
        data['hold_analysis']['receptor_runs'] = [
            {'lane': 0, 'lit': True, 'frames': 3, 'previous_seconds': .99,
             'start_seconds': 1.017, 'end_seconds': 1.05}]
        before = deepcopy(data)
        view = presentation(data)
        self.assertEqual(data, before)
        self.assertEqual(view['matches'][0]['judgment_label'], 'PERFECT')
        self.assertEqual(view['matches'][0]['observation_upper_seconds'], 1.017)
        self.assertEqual(view['judgment_events'][0]['status'], 'corroborating')
