from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.charts.policy import validate_regions, note_policy, apply_projection, attach_regions
from piu_timeline.play.ranges import timing_ranges


def region(**changes):
    return {'id': 'fast-scroll', 'start_seconds': 2, 'end_seconds': 4,
            'processing': 'exclude_timing', 'check_exceptions': ['timing_evidence'],
            'reason': 'Extreme speed changes prevent a reliable motion fit.', **changes}


def policy(*regions):
    return {'status': 'applied', 'regions': [{**r, 'playback_start_seconds': r['start_seconds']+10,
                                             'playback_end_seconds': r['end_seconds']+10} for r in regions]}


class ChartPolicyTest(unittest.TestCase):
    def test_region_validation_rejects_malformed_and_conflicting_settings(self):
        self.assertEqual(validate_regions({'regions': [region()]}), [region()])
        bad = [region(start_seconds=-1), region(end_seconds=2), region(end_seconds=float('nan')),
               region(processing='guess'), region(processing=[]), region(reason=''),
               region(check_exceptions=['all']), region(check_exceptions=['timing_evidence']*2), region(typo=True)]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_regions({'regions': [value]})
        for other in (region(), region(id='overlap', processing='hold_state_only')):
            with self.assertRaises(ValueError):
                validate_regions({'regions': [region(), other]})

    def test_half_open_song_regions_control_specific_checks_without_promoting_evidence(self):
        d = {'chart_policy': policy(region(processing='standard')),
             'notes': [{'status': 'estimated', 'lane': 0, 'target_seconds': t, 'prediction_uncertainty_seconds': .01} for t in (11.9,12,13,14)],
             'matches': [], 'combo_events': [], 'judgment_events': []}
        self.assertIsNone(note_policy(d, d['notes'][0]))
        self.assertIsNone(note_policy(d, d['notes'][3]))
        ranges = timing_ranges(d)
        self.assertEqual(ranges['counts'], {'unknown': 4})
        self.assertEqual(ranges['eligible_counts'], {'unknown': 2})
        self.assertEqual(ranges['notes'][1]['status'], 'unknown')

    def test_processing_suppresses_only_requested_links_and_retains_native_evidence(self):
        d = {'chart_policy': policy(region(processing='hold_state_only')),
             'notes': [{'status': 'estimated', 'lane': 0, 'target_seconds': 13, 'prediction_uncertainty_seconds': .01},
                       {'status': 'estimated', 'lane': 1, 'target_seconds': 13, 'prediction_uncertainty_seconds': .01,
                        'note_type': 'hold', 'hold_id': 0}],
             'matches': [{'note': 0, 'target_seconds': 13, 'observation_lower_seconds': 13, 'observation_upper_seconds': 13.02}],
             'hold_analysis': {'holds': [{'id': 0, 'display_note': 1, 'start_range': [12.99,13.01], 'end_range': [13.5,13.6],
                                         'input': {'segments': [{'lower_seconds':13.05,'upper_seconds':13.5}]}}]}}
        original = deepcopy(d); projected = apply_projection(d)
        self.assertEqual(d, original)
        self.assertEqual(projected['matches'], [])
        ranges = timing_ranges(projected)
        self.assertEqual(ranges['notes'][0]['status'], 'policy_excluded')
        self.assertEqual(ranges['notes'][1]['status'], 'hold_state')
        d['chart_policy'] = policy(region())
        projected = apply_projection(d)
        self.assertEqual(projected['hold_analysis']['holds'][0]['input']['segments'], [])
        self.assertEqual(projected['hold_analysis']['holds'][0]['input']['policy_retained_observations'], original['hold_analysis']['holds'][0]['input']['segments'])

    def test_current_metadata_is_mapped_from_its_own_seed_origin_and_refreshed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root/'repo'; output = root/'video/play/segment-001'; output.mkdir(parents=True)
            repo.mkdir(); (repo/'catalog.json').write_text(json.dumps({'songs':[{'title':'Example','index':'CS349'}]}))
            (repo/'aliases.json').write_text('{}')
            path = repo/'charts/CS349/S21/phoenix/metadata.json'; path.parent.mkdir(parents=True)
            d = {'song':'Example','chart':'S21','segment_number':1,'start_seconds':10,'end_seconds':20,
                 'media':{'size_bytes':123,'mtime_ns':456}}
            metadata = {'regions':[region()], 'alignment':{'song_start_seconds':10},
                        'source':{'source_id':'video','segment_number':1,'media_size_bytes':123,'media_mtime_ns':456,'playback_range':[10,20]}}
            path.write_text(json.dumps(metadata))
            with patch('piu_timeline.charts.audio.align',side_effect=AssertionError('Seed origin is already verified')):
                first = attach_regions(d, output, repo)
            self.assertEqual(first['chart_policy']['regions'][0]['playback_start_seconds'],12)
            (output/'chart-registration.json').write_text(json.dumps({'index':'CS349',
                'chart':str(repo/'charts/CS349/D22/phoenix/chart.ucs')}))
            same_chart = attach_regions(d, output, repo)
            self.assertEqual(same_chart['chart_policy']['metadata_path'], str(path))
            partial = attach_regions({**d, 'start_seconds':12, 'end_seconds':15}, output, repo)
            self.assertEqual(partial['chart_policy']['regions'][0]['playback_start_seconds'],12)
            metadata['regions'][0]['start_seconds'] = 3; path.write_text(json.dumps(metadata))
            again = attach_regions(d, output, repo)
            self.assertEqual(again['chart_policy']['regions'][0]['playback_start_seconds'],13)
            self.assertNotEqual(again['chart_policy']['metadata_sha256'], first['chart_policy']['metadata_sha256'])
            metadata['regions'][0]['processing'] = 'typo'; path.write_text(json.dumps(metadata))
            invalid = attach_regions(d, output, repo)
            self.assertEqual(invalid['chart_policy']['status'], 'invalid')
            self.assertEqual(invalid['chart_policy']['regions'], [])
