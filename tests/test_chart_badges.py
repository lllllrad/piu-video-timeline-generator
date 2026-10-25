import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from piu_timeline import chart_badges as badges, chart_badge_recovery as recovery
from piu_timeline.chart_data import canonical_chart
from piu_timeline.recognition import frame_labels, summary_stage_row


def line(text, x, y, w=.04, h=.02):
    return {'text': text, 'box': [x, y, w, h], 'confidence': .99}


def badge(number, x=.22, y=.29, stage=2):
    common = {'badge_read': True, 'badge_id': f'{x}-{stage}', 'badge_stage': stage,
              'badge_bounds': [x-.03, y-.04, .12, .15]}
    return [{**line('SINGLE', x, y), **common}, {**line(str(number), x, y+.03), **common}]


class BadgeTest(unittest.TestCase):
    def test_direct_badge_replaces_conflicting_local_glyphs_only(self):
        direct = badge(15, .64, .28, None)
        raw = [line('SINGLE', .64, .28), line('55', .64, .31), line('809', .65, .43)]
        labels = frame_labels(raw+direct, 'result')
        self.assertEqual(labels['chart']['text'], 'S15')
        self.assertIn(raw[-1], badges.prefer_badges(raw+direct))
        self.assertEqual(raw[1]['text'], '55')
        rival = line('RIVAL', .64, .01)
        self.assertIsNone(frame_labels(raw+direct+[rival], 'result')['chart'])

    def test_summary_badges_cannot_cross_observed_rows(self):
        lines = [line('1ST', .48, .18), line('Other', .46, .22),
                 line('2ND', .48, .31), line('Song', .46, .35)]
        rows = lines+badge(23, y=.16, stage=1)+badge(21, y=.29, stage=2)
        self.assertEqual(summary_stage_row(rows, 1)['chart']['text'], 'S23')
        self.assertEqual(summary_stage_row(rows, 2)['chart']['text'], 'S21')
        wrong = lines+badge(23, y=.29, stage=1)
        self.assertIsNone(summary_stage_row(wrong, 2)['chart'])

    def test_numeral_variants_must_agree_and_keep_source_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'frame.png'
            image = np.zeros((100, 100, 3), np.uint8)
            image[30:60, 30:40] = 255
            cv2.imwrite(str(path), image)
            original = path.read_bytes()
            regions = [{'pixels': [0, 0, 100, 100], 'player_id': 'p1', 'stage': None}]
            def ocr(paths, english=False, single_line=False):
                return [{'lines': [line('15' if i == 0 else '55', 0, 0)]} for i, _ in enumerate(paths)] if single_line else [
                    {'lines': [line('SINGLE', .25, .2, .4, .1)]} for _ in paths]
            with patch.object(badges, 'badge_regions', return_value=regions), patch.object(badges, 'ocr_images', side_effect=ocr):
                self.assertEqual(badges.read_badges(path, 'result', []), [])
            self.assertEqual(path.read_bytes(), original)

    def test_basic_mode_canonical_identity_requires_distinct_verified_pts(self):
        data = {'chart': 'VERY HARD 12', 'chart_identity': {
            'chart': 'S12', 'display_chart': 'VERY HARD 12', 'status': 'recognized',
            'method': 'matching_title_summary_badge', 'source_frames': [
                {'file': 'a', 'source_pts_seconds': 1}, {'file': 'b', 'source_pts_seconds': 2}]}}
        self.assertEqual(canonical_chart(data), 'S12')
        self.assertEqual(data['chart'], 'VERY HARD 12')
        for key, value in [('chart', 'D12'), ('display_chart', 'VERY HARD 11'), ('method', 'guess')]:
            invalid = copy.deepcopy(data);invalid['chart_identity'][key] = value
            self.assertIsNone(canonical_chart(invalid))
        data['chart_identity']['source_frames'][1]['source_pts_seconds'] = 1
        self.assertIsNone(canonical_chart(data))

    def recover(self, tmp, times=(1, 2), song='Song', raw=None, blocked=False):
        directory = Path(tmp);folder = directory/'evidence/segment-001';folder.mkdir(parents=True)
        frames = []
        for i, pts in enumerate(times):
            image = folder/f'frame-{i}.png';image.write_bytes(b'retained source image')
            lines = [line('2ND', .48, .31), line('Song', .46, .35)]
            frames.append({'file': str(image), 'source_pts_seconds': pts, 'phase': 'summary',
                           'focused_ocr': lines, 'ocr': [line('RIVAL', .25, .01)] if blocked else []})
        ocr = folder/'ocr.json';ocr.write_text(json.dumps(frames))
        segment = {'song': song, 'chart': raw, 'players': {'p1': {}}, 'ocr_evidence': str(ocr),
                   'summary_evidence': [frame['file'] for frame in frames], 'results': {
                       'players': {}, 'status': 'not_displayed', 'needs_review': False}}
        return {'segments': [segment]}, directory

    def test_summary_recovery_matches_title_and_original_pts_and_is_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            document, directory = self.recover(tmp)
            with patch.object(recovery, 'read_badges', return_value=badge(21)) as read:
                self.assertTrue(recovery.refresh(document, directory))
                self.assertEqual(document['segments'][0]['chart'], 'S21')
                self.assertEqual(read.call_count, 2)
                self.assertEqual(document['segments'][0]['results']['players'], {})
                self.assertFalse(recovery.refresh(document, directory))
                self.assertEqual(read.call_count, 2)

    def test_wrong_title_duplicate_pts_and_rival_never_confirm_chart(self):
        for kwargs in ({'song': 'Other'}, {'times': (1, 1)}, {'blocked': True}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as tmp:
                document, directory = self.recover(tmp, **kwargs)
                with patch.object(recovery, 'read_badges', return_value=badge(21)) as read:
                    recovery.refresh(document, directory)
                    self.assertIsNone(document['segments'][0]['chart'])
                    count = read.call_count
                    recovery.refresh(document, directory)
                    self.assertEqual(read.call_count, count)

    def test_basic_mode_preserves_display_and_adds_canonical_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            document, directory = self.recover(tmp, raw='VERY HARD 12')
            with patch.object(recovery, 'read_badges', return_value=badge(12)):
                self.assertTrue(recovery.refresh(document, directory))
            segment = document['segments'][0]
            self.assertEqual(segment['chart'], 'VERY HARD 12')
            self.assertEqual(canonical_chart(segment), 'S12')
            self.assertEqual(len(segment['chart_identity']['source_frames']), 2)

    def test_result_badge_recovers_conflict_without_changing_judgment_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            frames = []
            for pts in (10, 11):
                path = directory/f'{pts}.png'
                path.write_bytes(b'original image')
                frames.append({'file': str(path), 'source_pts_seconds': pts, 'phase': 'result',
                               'identity_eligible': True, 'focused_ocr': [line('Song', .4, .16, .2)]})
            ocr = directory/'ocr.json';ocr.write_text(json.dumps(frames))
            fields = {'chart': {'value': None, 'status': 'conflict'},
                      'perfect': {'value': 809, 'status': 'recognized'}}
            result_player = {'presence': 'recognized', 'chart': None, 'perfect': 809,
                             'fields': fields, 'needs_review': True}
            segment = {'song': 'Song', 'chart': None, 'ocr_evidence': str(ocr), 'players': {'p2': {}},
                       'results': {'players': {'p2': result_player}, 'needs_review': True}}
            with patch.object(recovery, 'read_badges', return_value=badge(15, .64, .28, None)):
                recovery.refresh({'segments': [segment]}, directory)
            self.assertEqual(segment['chart'], 'S15')
            self.assertEqual(result_player['chart'], 'S15')
            self.assertEqual(result_player['perfect'], 809)
            self.assertEqual(fields['perfect'], {'value': 809, 'status': 'recognized'})
            self.assertFalse(result_player['needs_review'])
