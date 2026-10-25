"""Repeated pre-receptor visibility loss must not become input evidence."""
import copy
import unittest

from piu_timeline.play.channels import annotate_matches
from piu_timeline.play.processing import processing_support, processing_conflicts
from piu_timeline.play.visibility import pre_receptor_losses


def losses(count=8, height=.85, step=.2):
    return [{'note': i, 'lane': i%3, 'status': 'disappeared_near_receptor',
             'range': [i*step, i*step+.017], 'source_pts_seconds': [40+i*step, 40+i*step+.017],
             'confirmation_source_pts_seconds': 40+i*step+.034,
             'samples': [{'time': i*step, 'pts': 40+i*step, 'state': 'present', 'y': 20+height*30}]}
            for i in range(count)]


class VisibilityTest(unittest.TestCase):
    def test_repeated_spatial_loss_preserves_raw_proof_without_consumption_or_conflict(self):
        records = losses(); original = copy.deepcopy(records)
        boundaries = pre_receptor_losses(records, 20, 30)
        self.assertEqual(boundaries[0]['notes'], list(range(8)))
        self.assertEqual(boundaries[0]['last_visible_height_spacing'], [.85,.85])
        for record, previous in zip(records, original):
            self.assertEqual(record['status'], 'unresolved')
            self.assertEqual(record['reason'], 'pre_receptor_visibility_boundary')
            self.assertEqual(record['samples'], previous['samples'])
            self.assertNotIn('range', record)
            self.assertEqual(record['visibility_loss']['range'], previous['range'])
            self.assertEqual(record['visibility_loss']['source_pts_seconds'], previous['source_pts_seconds'])
            self.assertEqual(record['visibility_loss']['confirmation_source_pts_seconds'], previous['confirmation_source_pts_seconds'])
        data = {'visual_channels': {'processing': {'notes': records}},
                'matches': [{'note': 0, 'observation_lower_seconds': .18,
                             'observation_upper_seconds': .2, 'processing_conflict': True}]}
        self.assertIsNone(processing_support(data, 0, 0, .017))
        self.assertFalse(processing_conflicts(data, 0, .18, .2))
        self.assertNotIn('processing_conflict', annotate_matches(data)['matches'][0])

    def test_near_receptor_sparse_single_lane_and_nonstationary_losses_are_not_boundaries(self):
        single_lane = losses()
        for record in single_lane:
            record['lane'] = 0
        moving = losses()
        for i, record in enumerate(moving):
            record['samples'][0]['y'] += i*3
        for records in (losses(height=.3), losses(count=7), losses(step=4), losses(step=.05), single_lane, moving):
            with self.subTest(records=records):
                original = copy.deepcopy(records)
                self.assertEqual(pre_receptor_losses(records,20,30), [])
                self.assertEqual(records, original)
