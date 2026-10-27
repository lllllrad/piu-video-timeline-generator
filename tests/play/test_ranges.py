import unittest
import json
import tempfile
from pathlib import Path

from piu_timeline.play.ranges import timing_ranges, counter_frame_ranges


def note(target):
    return {'status': 'estimated', 'target_seconds': target, 'prediction_uncertainty_seconds': .01}


def match(index, target, lo, hi):
    return {'note': index, 'target_seconds': target, 'observation_lower_seconds': lo,
            'observation_upper_seconds': hi}


class TimingRangeTest(unittest.TestCase):
    def test_processing_conflict_retains_raw_bracket_without_confirming_input_or_bounding_neighbors(self):
        assigned={**match(0,9,9.01,9.02),'processing_conflict':True}
        data={'notes':[note(9),note(10),note(11)],'matches':[assigned,match(2,11,11.01,11.02)]}
        records=timing_ranges(data)['notes']
        self.assertEqual(records[0]['status'],'conflicted')
        self.assertEqual(records[0]['observed_input_range'],[9.01,9.02])
        self.assertEqual(records[0]['input_ranges'],[])
        self.assertNotEqual(records[1]['status'],'bounded')

    def test_delayed_nearby_processing_retains_disjoint_alternatives(self):
        data = {'notes': [note(10)], 'combo_events': [
            {'delta': 1, 'lower_seconds': 10.12, 'upper_seconds': 10.14, 'reason': 'ambiguous'},
            {'delta': 2, 'lower_seconds': 10.2, 'upper_seconds': 10.23},
            {'delta': -5, 'lower_seconds': 10, 'upper_seconds': 10.02}],
            'judgment_events': [{'label': 'MISS', 'lower_seconds': 10, 'upper_seconds': 10.02}]}
        result = timing_ranges(data)
        record = result['notes'][0]
        self.assertEqual(record['status'], 'possible')
        self.assertEqual(record['input_ranges'], [[10.12, 10.14], [10.2, 10.23]])
        self.assertEqual(len(record['alternatives']), 2)
        self.assertEqual(result['counts'], {'possible': 1})
        self.assertNotIn('matches', data)

    def test_neighbors_supply_conditional_bounds_not_a_confirmed_press(self):
        data = {'notes': [note(9), note(10), note(11)],
                'matches': [match(0, 9, 9.01, 9.02), match(2, 11, 11.01, 11.02)]}
        record = timing_ranges(data)['notes'][1]
        self.assertEqual(record['status'], 'bounded')
        self.assertEqual(record['input_ranges'], [[9.75, 10.5]])
        self.assertEqual(record['neighbor_observation_range'], [9.01, 11.02])
        self.assertEqual(record['anchors'], [0, 2])
        self.assertIn('do not establish a press', record['condition'])
        data['notes'][2] = note(15)
        data['matches'][1] = match(2, 15, 15.01, 15.02)
        self.assertEqual(timing_ranges(data)['notes'][1]['status'], 'unknown')

    def test_miss_never_gets_a_press_even_with_nearby_positive_evidence(self):
        data = {'notes': [note(10)], 'miss_candidates': [{'note': 0}],
                'combo_events': [{'delta': 1, 'lower_seconds': 10, 'upper_seconds': 10.02}]}
        record = timing_ranges(data)['notes'][0]
        self.assertEqual(record['status'], 'possible_miss')
        self.assertEqual(record['input_ranges'], [])

    def test_correction_changes_search_but_preserves_original_observation_times(self):
        data = {'notes': [note(10)], 'display_delay_correction_ms': 200,
                'judgment_events': [{'label': 'GREAT', 'lower_seconds': 10.6, 'upper_seconds': 10.62}]}
        self.assertEqual(timing_ranges(data)['notes'][0]['input_ranges'], [[10.6, 10.62]])
        data['display_delay_correction_ms'] = 0
        self.assertEqual(timing_ranges(data)['notes'][0]['status'], 'unknown')

    def test_exact_match_retains_wide_aggregate_bracket_without_extra_alternatives(self):
        data = {'notes': [note(10)], 'matches': [match(0, 10, 9.8, 10.2)]}
        record = timing_ranges(data)['notes'][0]
        self.assertEqual(record['status'], 'matched')
        self.assertEqual(record['input_ranges'], [[9.8, 10.2]])

    def test_native_counter_changes_keep_pts_and_reject_reset_and_long_gap(self):
        frames = [{'playback_seconds': time, 'source_pts_seconds': time + 100,
                   'combo': value, 'combo_confidence': confidence}
                  for time, value, confidence in ((1, 5, .99), (1.01, None, 0), (1.02, 6, .9),
                                                   (1.03, 4, .95), (2.1, 7, .99),
                                                   (2.15, 8, .2), (2.2, 8, .9))]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'frames.jsonl'
            path.write_text(''.join(json.dumps(frame) + '\n' for frame in frames))
            events = counter_frame_ranges(path)
        self.assertEqual([(event['before'], event['after']) for event in events], [(5, 6), (7, 8)])
        self.assertEqual(events[0]['source_pts_seconds'], [101, 101.02])
        self.assertEqual((events[0]['lower_seconds'], events[0]['upper_seconds']), (1, 1.02))

    def test_confirmed_bracket_is_limited_but_original_evidence_remains_available(self):
        data = {'notes': [note(10)], 'matches': [match(0, 10, 9, 11)]}
        record = timing_ranges(data)['notes'][0]
        self.assertEqual(record['input_ranges'], [[9.75, 10.5]])
        self.assertEqual(record['observed_input_range'], [9, 11])
        self.assertEqual(data['matches'][0]['observation_lower_seconds'], 9)
        data['matches'][0] = match(0, 10, 10.501, 10.52)
        record = timing_ranges(data)['notes'][0]
        self.assertEqual(record['input_ranges'], [])
        self.assertEqual(record['status'], 'unknown')
        self.assertEqual(record['reason'], 'outside_association_window')

    def test_possible_ranges_use_only_the_intersection_of_the_original_bracket(self):
        data = {'notes': [note(10)], 'combo_events': [
            {'delta': 1, 'lower_seconds': 9, 'upper_seconds': 11}]}
        record = timing_ranges(data)['notes'][0]
        self.assertEqual(record['input_ranges'], [[9.75, 10.5]])
        self.assertEqual(record['alternatives'][0]['lower_seconds'], 9)
        self.assertEqual(record['alternatives'][0]['upper_seconds'], 11)
