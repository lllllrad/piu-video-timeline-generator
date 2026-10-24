from copy import deepcopy
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from piu_timeline.play_holds import detect_bodies, reconstruct, presentation, feature_contract, augment_holds, acquire_features, contextual_hold_support


LAYOUT = {'receptor_y': .15, 'note_y_max': .95,
          'lanes': [{'x': .38 + .06*i, 'color': 'blue', 'name': str(i)} for i in range(5)]}


class HoldTest(unittest.TestCase):
    def test_dim_short_hold_pulse_requires_local_change_body_and_positive_update(self):
        frames = [{'playback_seconds': i*.017, 'source_pts_seconds': 10+i*.017,
                   'receptor_white_fraction': [.1, .26, .1, .1, .1],
                   'receptor_lit': [False]*5, 'bodies': [], 'common_receptor_flash': False} for i in range(20)]
        frame = frames[10]
        frame['receptor_white_fraction'][1] = .5
        frame['bodies'] = [{'lane': 1, 'top': 20, 'bottom': 80}]
        data = {'combo_events': [{'delta': 1, 'lower_seconds': .17, 'upper_seconds': .187}]}
        result = contextual_hold_support(data, frames, 20, 20)
        self.assertEqual(list(result), [(10, 1)])
        self.assertEqual(result[(10, 1)][0]['kind'], 'combo_events')
        self.assertFalse(contextual_hold_support({}, frames, 20, 20))
        data['combo_events'][0]['delta'] = -1
        self.assertFalse(contextual_hold_support(data, frames, 20, 20))
        data = {'judgment_events': [{'label': 'MISS', 'lower_seconds': .17, 'upper_seconds': .187}]}
        self.assertFalse(contextual_hold_support(data, frames, 20, 20))
        data['judgment_events'][0]['label'] = 'PERFECT'
        self.assertIn((10, 1), contextual_hold_support(data, frames, 20, 20))
        frame['common_receptor_flash'] = True
        self.assertFalse(contextual_hold_support(data, frames, 20, 20))
        frame['common_receptor_flash'] = False; frame['bodies'] = []
        self.assertFalse(contextual_hold_support(data, frames, 20, 20))
        frame['bodies'] = [{'lane': 1, 'top': 20, 'bottom': 80}]
        for previous in frames[:10]:
            previous['receptor_white_fraction'][1] = .5
        self.assertFalse(contextual_hold_support(data, frames, 20, 20))

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
        # A single dim frame needs a local pulse, body and positive HUD update.
        dim = deepcopy(frames)
        for frame in dim:
            frame['receptor_lit'] = [False]*5
            frame['receptor_white_fraction'] = [.1]*5
        dim[45]['receptor_white_fraction'][2] = .5
        contextual_data = {**data, 'combo_events': [{'delta': 1, 'lower_seconds': .9, 'upper_seconds': .92}]}
        recovered_dim = reconstruct(contextual_data, dim)
        self.assertEqual(len(recovered_dim), 1)
        self.assertEqual(recovered_dim[0]['input']['segments'][0]['frames'], 1)
        self.assertEqual(recovered_dim[0]['input']['segments'][0]['contextual_frames'], 1)
        self.assertEqual(recovered_dim[0]['input']['segments'][0]['first_source_pts_seconds'], 10.9)
        self.assertFalse(reconstruct(data, dim)[0]['input']['segments'])
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
                       'bodies': [], 'receptor_lit': [False]*5, 'receptor_white_fraction':[0]*5} for time in (0, .02)]
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
        # Light can first become distinguishable after the judgment refresh.
        data['hold_analysis']['receptor_runs']=[{'lane':1,'lit':True,'frames':3,
            'previous_seconds':1.56,'previous_lit':None,'start_seconds':1.58,'end_seconds':1.62,
            'onset_range':[1.48,1.58],'onset_source_pts_seconds':[101.48,101.58]}]
        supported = presentation(data)
        self.assertEqual(supported['matches'],data['matches'])
        self.assertEqual(supported['matches'][0]['combo_upper_seconds'],1.51)
        data['hold_analysis']['receptor_runs'][0]['onset_range']=None
        self.assertEqual(presentation(data)['matches'],[])

    def test_one_obscured_onset_cannot_confirm_two_repeated_taps_during_a_hold(self):
        hold={'id':0,'lane':0,'start_range':[1,1.02],'end_range':[2,2.02],
              'start_censored':False,'end_censored':False,'head_note':0,
              'covered_notes':[0],'input':{'segments':[]}}
        data={'notes':[{'status':'estimated','lane':0,'target_seconds':1.01},
                       {'status':'estimated','lane':1,'target_seconds':1.5},
                       {'status':'estimated','lane':1,'target_seconds':1.6}],
              'matches':[{'note':i,'target_seconds':t,'combo_event':i-1,
                          'combo_lower_seconds':t,'combo_upper_seconds':t+.01} for i,t in [(1,1.5),(2,1.6)]],
              'hold_analysis':{'holds':[hold],'receptor_runs':[
                  {'lane':1,'lit':True,'frames':4,'previous_seconds':1.61,'previous_lit':None,
                   'start_seconds':1.63,'end_seconds':1.7,'onset_range':[1.49,1.63]}]}}
        original=deepcopy(data)
        ambiguous=presentation(data)
        self.assertEqual(ambiguous['matches'],[])
        self.assertEqual(ambiguous['hold_tick_ambiguous_notes'],[1,2])
        self.assertEqual(data,original)
        # Two independently observed transitions can corroborate two presses.
        data['hold_analysis']['receptor_runs']=[
            {'lane':1,'lit':True,'frames':2,'previous_seconds':t-.01,'previous_lit':False,
             'start_seconds':t,'end_seconds':t+.02,'onset_range':[t-.01,t]}
            for t in (1.5,1.6)]
        self.assertEqual(presentation(data)['matches'],data['matches'])
