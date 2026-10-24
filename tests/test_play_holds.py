from copy import deepcopy
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from piu_timeline.play_holds import detect_bodies, reconstruct, presentation, feature_contract, augment_holds, acquire_features


LAYOUT = {'receptor_y': .15, 'note_y_max': .95,
          'lanes': [{'x': .38 + .06*i, 'color': 'blue', 'name': str(i)} for i in range(5)]}


class HoldTest(unittest.TestCase):
    def test_moving_long_body_and_filled_receptor_form_one_sustained_note(self):
        width, height = 325, 183
        spacing = .06*width
        receptor = .15*height
        frames = []
        for i in range(111):
            time = i*.02
            top = max(receptor+.3*spacing, receptor+200*(.6-time)-.45*spacing)
            bottom = min(.95*height-1, receptor+200*(1.6-time)+.45*spacing)
            image = np.zeros((height, width, 3), dtype='uint8')
            x = round(.5*width)
            if bottom > top:
                cv2.rectangle(image, (x-5, round(top)), (x+5, round(bottom)), (0, 130, 255), -1)
            if .6 <= time <= 1.6:
                cv2.rectangle(image, (x-5, round(receptor)-5), (x+5, round(receptor)+5), (255, 255, 255), -1)
            bodies, lit = detect_bodies(image, LAYOUT)
            frames.append({'playback_seconds': time, 'source_pts_seconds': time+10,
                           'bodies': bodies, 'receptor_lit': lit})
        data = {'layout': LAYOUT, 'game_roi': [0, 0, 325, 183], 'start_seconds': 0, 'end_seconds': 2.2,
                'notes': [{'status': 'estimated', 'lane': 2, 'target_seconds': .6,
                           'prediction_uncertainty_seconds': .01},
                          {'status': 'estimated', 'lane': 2, 'target_seconds': 1.58,
                           'prediction_uncertainty_seconds': .01}]}
        holds = reconstruct(data, frames)
        self.assertEqual(len(holds), 1, holds)
        hold = holds[0]
        self.assertFalse(hold['start_censored'])
        self.assertAlmostEqual(sum(hold['start_range'])/2, .6, delta=.08)
        self.assertIsNotNone(hold['end_range'])
        self.assertAlmostEqual(sum(hold['end_range'])/2, 1.6, delta=.1)
        self.assertTrue(hold['input']['segments'])
        self.assertIsNone(hold['input']['press_range'])
        self.assertIsNone(hold['input']['release_range'])
        self.assertGreater(hold['input']['segments'][0]['frames'], 10)
        partial = reconstruct({**data, 'end_seconds': 1}, [frame for frame in frames if frame['playback_seconds'] < 1])
        self.assertTrue(partial)
        self.assertTrue(partial[0]['end_censored'])
        self.assertIsNone(partial[0]['end_range'])
        obscured = deepcopy(frames)
        for item in obscured:
            if .65 < item['playback_seconds'] < .75:
                item['bodies'] = []
        recovered = reconstruct(data, obscured)
        self.assertEqual(len(recovered), 1)
        self.assertTrue(any(segment['lower_seconds'] <= .66 and segment['upper_seconds'] >= .74
                            for segment in recovered[0]['input']['segments']))

    def test_projection_suppresses_ticks_and_tail_without_mutating_native_taps(self):
        hold = {'id': 0, 'lane': 0, 'start_range': [1, 1.02], 'end_range': [2, 2.02],
                'start_censored': False, 'end_censored': False, 'head_note': 0,
                'covered_notes': [0, 1], 'input': {'segments': [{'lower_seconds': 1.01, 'upper_seconds': 2}]}}
        data = {'notes': [{'status': 'estimated', 'lane': 0, 'target_seconds': 1.01},
                          {'status': 'estimated', 'lane': 0, 'target_seconds': 2.01},
                          {'status': 'estimated', 'lane': 1, 'target_seconds': 1.5}],
                'matches': [{'note': 0}, {'note': 1}, {'note': 2}], 'hold_analysis': {'holds': [hold]}}
        original = deepcopy(data)
        result = presentation(data)
        self.assertEqual(data, original)
        self.assertEqual(result['notes'][0]['note_type'], 'hold')
        self.assertEqual(result['notes'][1]['status'], 'excluded')
        self.assertEqual(result['matches'], [{'note': 2}])
        self.assertEqual(result['coverage']['long_notes'], 1)
        self.assertEqual(result['coverage']['timed_note_heads'], 1)

    def test_plain_tap_has_no_long_body_and_static_receptor_is_not_hold_input(self):
        image = np.zeros((183, 325, 3), dtype='uint8')
        cv2.rectangle(image, (157, 100), (167, 112), (0, 130, 255), -1)
        bodies, lit = detect_bodies(image, LAYOUT)
        self.assertFalse(any(body['long'] for body in bodies))
        self.assertFalse(any(lit))

    def test_cached_pixel_features_refit_and_then_replay_without_decoding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source.mkv'; source.write_bytes(b'original recording')
            data = {'media': {'path': str(source), 'video_streams': [{'index': 0}]},
                    'layout': LAYOUT, 'game_roi': [0, 0, 325, 183], 'notes': [],
                    'start_seconds': 0, 'end_seconds': 1}
            (root / 'hold-features.json').write_text(json.dumps({'contract': feature_contract(data)}))
            frames = [{'playback_seconds': time, 'source_pts_seconds': time+10,
                       'bodies': [], 'receptor_lit': [False]*5} for time in (0, .02)]
            (root / 'hold-frames.jsonl').write_text(''.join(json.dumps(frame)+'\n' for frame in frames))
            with patch('piu_timeline.play_holds.decode_frames', side_effect=AssertionError('cached pixels')):
                result = augment_holds(data, root)
            self.assertEqual(result['hold_analysis']['holds'], [])
            self.assertTrue(result['hold_analysis']['receptor_runs'])
            with patch('piu_timeline.play_holds.decode_frames', side_effect=AssertionError('cached pixels')), \
                    patch('piu_timeline.play_holds.reconstruct', side_effect=AssertionError('cached associations')):
                replay = augment_holds(data, root)
            self.assertEqual(replay['hold_analysis'], result['hold_analysis'])
            self.assertEqual(source.read_bytes(), b'original recording')

    def test_pts_mismatch_does_not_overwrite_old_hold_features(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source.mkv'; source.write_bytes(b'original')
            data = {'media': {'path': str(source)}, 'layout': LAYOUT, 'game_roi': [0, 0, 325, 183],
                    'start_seconds': 0, 'end_seconds': 1}
            (root / 'frames.jsonl').write_text(json.dumps({'source_pts_seconds': 10, 'playback_seconds': 0})+'\n')
            old = root / 'hold-frames.jsonl';old.write_text('previous pixels')
            decoded = [(10.1, .1, np.zeros((183, 325, 3), dtype='uint8'))]
            with patch('piu_timeline.play_holds.decode_frames', return_value=iter(decoded)):
                with self.assertRaisesRegex(ValueError, 'PTS differs'):
                    acquire_features(data, root)
            self.assertEqual(old.read_text(), 'previous pixels')
            self.assertFalse(root.joinpath('hold-frames.build-jsonl').exists())

    def test_separate_tap_heads_do_not_supply_a_continuous_hold_stripe(self):
        image = np.zeros((183, 325, 3), dtype='uint8')
        for top in (80, 106):
            cv2.rectangle(image, (157, top), (167, top+16), (0, 130, 255), -1)
        bodies, _ = detect_bodies(image, LAYOUT)
        # A small morphological gap repair must not turn stacked taps into
        # long-note evidence: the original unfilled stripe remains auditable.
        self.assertFalse(any(body['long'] and body['stripe_support'] >= .8 for body in bodies))

    def test_other_lane_tap_during_hold_requires_its_own_receptor_onset(self):
        hold = {'id':0,'lane':0,'start_range':[1,1.02],'end_range':[2,2.02],
                'start_censored':False,'end_censored':False,'head_note':0,
                'covered_notes':[0], 'input':{'segments':[]}}
        data = {'notes':[{'status':'estimated','lane':0,'target_seconds':1.01},
                         {'status':'estimated','lane':1,'target_seconds':1.5}],
                'matches':[{'note':1,'target_seconds':1.5,'combo_event':0,
                            'combo_lower_seconds':1.49,'combo_upper_seconds':1.51}],
                'combo_events':[{'lower_seconds':1.49,'upper_seconds':1.51,'delta':1}],
                'hold_analysis':{'holds':[hold]}}
        ambiguous = presentation(data)
        self.assertEqual(ambiguous['matches'],[])
        self.assertEqual(ambiguous['hold_tick_ambiguous_notes'],[1])
        data['hold_analysis']['receptor_runs']=[{'lane':1,'lit':True,'frames':3,
            'previous_seconds':1.48,'start_seconds':1.49,'end_seconds':1.55}]
        supported = presentation(data)
        self.assertEqual(supported['matches'],data['matches'])
        self.assertEqual(supported['combo_events'][0]['reason'],'tap_with_independent_lane_onset_during_hold')
