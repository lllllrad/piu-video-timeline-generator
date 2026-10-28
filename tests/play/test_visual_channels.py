"""Independent pixel disappearance, retained channel evidence and association controls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from piu_timeline.play.channels import annotate_matches, collect
from piu_timeline.play.holds.features import feature_contract
from piu_timeline.play.processing import ReceptorPixels, observe_processing
from piu_timeline.play.recovery import recover_rows


def pixel_play(directory, kind='consumed'):
    layout = {'lanes': [{'x': .2+.1*i, 'color': 'blue'} for i in range(5)],
              'receptor_y': .3, 'note_y_max': .95}
    data = {'layout': layout, 'media': {}, 'game_roi': [0,0,325,200],
            'analysis_width':325, 'analysis_height':200, 'start_seconds':0, 'end_seconds':1.4,
            'notes':[{'lane':2, 'status':'estimated', 'target_seconds':1.,
                      'prediction_uncertainty_seconds':.01, 'velocity_pixels_per_second':-200., 'points':[]}],
            'matches':[], 'hold_analysis': {'holds': [], 'receptor_runs': []},
            'combo_events':[], 'judgment_events':[]}
    pixels = ReceptorPixels(layout, 325, 200)
    frames = []
    for i in range(84):
        time = i/60
        if kind == 'gap' and .99 < time < 1.09:
            continue
        if kind == 'truncated' and time > 1:
            break
        image = np.full((200,325,3), 70, dtype='uint8')
        y, x = round(60+200*(1-time)), 130
        visible = time < 1 or kind in ('passed', 'reappeared')
        if kind == 'reappeared' and 1 <= time < 1.04:
            visible = False
        if visible and 15 <= y < 185:
            cv2.rectangle(image, (x-14,y-14), (x+14,y+14), (255,255,255), -1)
            cv2.rectangle(image, (x-11,y-11), (x+11,y+11), (0,130,255), -1)
            if y > 60+32.5*.85:
                data['notes'][0]['points'].append([time,y])
        if kind in ('flash','long_flash') and 1 <= time <= (1.04 if kind == 'flash' else 1.25):
            image[35:90,110:150] = 255
        if kind == 'partial_flash' and time >= 1:
            # A narrow bright core plus desaturated bloom covers the head.
            # Whole-patch white fraction stays below the old 45% cutoff.
            image[y-14:y+15,x-14:x+15] = (160,210,240)
            image[y-14:y+15,x-4:x+4] = 255
        if kind == 'cut' and time >= 1:
            image[:] = 0
        pixels.observe(image, time+42, time)
        frames.append({'source_pts_seconds':time+42, 'playback_seconds':time,
                       'notes':[], 'combo':None, 'receptor_lit':[False]*5})
    if kind == 'neighbor':
        data['notes'].append({**data['notes'][0], 'target_seconds':1.1})
    if kind == 'hold':
        data['hold_analysis']['holds'] = [{'id':0, 'lane':2, 'covered_notes':[0], 'start_range':[.99,1.01],
                                            'end_range':None, 'end_censored':True}]
    pixels.save(directory/'processing-features.npz', feature_contract(data))
    return data, frames


class VisualChannelTest(unittest.TestCase):
    def test_hud_changes_reuse_native_processing_and_type_measurements(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); data, frames = pixel_play(directory)
            (directory/'frames.jsonl').write_text(''.join(json.dumps(frame)+'\n' for frame in frames))
            before = collect(data, directory, frames)
            data['judgment_events'] = [{'lower_seconds': 59/60, 'upper_seconds': 1., 'label': 'GREAT'}]
            data['hold_analysis']['receptor_runs'] = [{'lane': 2, 'lit': True, 'frames': 3, 'start_seconds': 1., 'end_seconds': 1.04, 'onset_range': [.98, 1.]}]
            with patch('piu_timeline.play.channels.observe_processing', side_effect=AssertionError('must reuse native processing')), \
                    patch('piu_timeline.play.channels.observe_types', side_effect=AssertionError('must reuse native type reads')):
                after = collect(data, directory, frames)
            self.assertEqual(after['processing'], before['processing'])
            self.assertEqual(after['note_types'], before['note_types'])
            self.assertEqual(len(after['popup']['judgment_events']), 1)
            self.assertEqual(after['popup']['judgment_events'][0]['source_pts_seconds'], [42+59/60, 43.])

    def test_measurement_consumers_fail_when_acquisition_is_missing_without_decoding(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); data, frames = pixel_play(directory)
            data['media'] = {'video_streams': [{'index': 0}]}
            frames[0]['notes'] = [{'lane': 2, 'x': .4, 'y': .8}]
            from piu_timeline.play.appearance import retained
            from piu_timeline.play.receptors import observations
            with patch('piu_timeline.play.appearance.decode_frames', side_effect=AssertionError('consumer must not decode')), \
                    self.assertRaisesRegex(ValueError, 'acquisition stage'):
                retained(data, directory, frames)
            missing = [{k: v for k, v in f.items() if k != 'receptor_white_fraction'} for f in frames]
            with patch('piu_timeline.play.receptors.decode_frames', side_effect=AssertionError('consumer must not decode')), \
                    self.assertRaisesRegex(ValueError, 'acquisition stage'):
                observations(data, directory, missing, allow_decode=False)

    def test_pixels_distinguish_consumption_passage_and_unknown_without_hud_or_light(self):
        for kind, expected in [('consumed','disappeared_near_receptor'), ('passed','passed_target'),
                               ('reappeared','passed_target'), ('flash','disappeared_near_receptor'),
                               ('long_flash','unresolved'), ('partial_flash','unresolved'), ('cut','unresolved'),
                               ('gap','unresolved'), ('truncated','unresolved'), ('neighbor','unresolved'),
                               ('hold','hold_component')]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                data, _ = pixel_play(directory, kind)
                event = observe_processing(data, directory/'processing-features.npz')['notes'][0]
                self.assertEqual(event['status'], expected, event)
                if kind == 'consumed':
                    self.assertAlmostEqual(event['range'][1],1.)
                    self.assertEqual(event['source_pts_seconds'], [42+59/60,43.])
                    self.assertAlmostEqual(event['confirmation_source_pts_seconds'],43+1/60)

    def test_all_channels_keep_unassigned_events_unknown_frames_and_original_pts(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); data, frames = pixel_play(directory)
            data['combo_events'] = [{'lower_seconds':59/60,'upper_seconds':1.,'delta':1}]
            data['judgment_events'] = [{'lower_seconds':59/60,'upper_seconds':1.,'label':'GREAT'}]
            frames[60]['receptor_lit'][0] = None
            (directory/'frames.jsonl').write_text(''.join(json.dumps(f)+'\n' for f in frames))
            words = [{**f,'label':None,'blank':False} for f in frames]
            (directory/'judgments.jsonl').write_text(''.join(json.dumps(f)+'\n' for f in words))
            channels = collect(data, directory, frames)
            self.assertEqual(channels['popup']['combo_events'][0]['source_pts_seconds'], [42+59/60,43.])
            self.assertEqual(channels['popup']['judgment_frame_counts'], {'unknown':84})
            self.assertEqual(channels['receptors']['unknown_lane_frames'],1)
            self.assertEqual(channels['processing']['notes'][0]['status'],'disappeared_near_receptor')
            self.assertEqual(data['matches'],[])
            frames[0]['source_pts_seconds'] += 1
            with self.assertRaisesRegex(ValueError,'timestamps differ'):
                collect(data,directory,frames)

    def test_disappearance_can_own_a_hud_refresh_without_receptor_onset_but_not_invent_input(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); data, _ = pixel_play(directory)
            data['visual_channels'] = {'processing':observe_processing(data,directory/'processing-features.npz')}
            data['judgment_events'] = [{'label':'GREAT','lower_seconds':59/60,'upper_seconds':1.,'delta':1}]
            matches, recovered = recover_rows(data)
            self.assertEqual(recovered,[0])
            self.assertEqual(matches[0]['observation_upper_seconds'],1.)
            self.assertEqual(matches[0]['processing_source_pts_seconds'],[42+59/60,43.])
            projected = annotate_matches({**data,'matches':matches})
            self.assertIn('processing:0',projected['matches'][0]['visual_evidence'])
            self.assertIn('judgment:0',projected['matches'][0]['visual_evidence'])
            data['judgment_events'][0]['label'] = 'MISS'
            self.assertEqual(recover_rows(data)[1],[])
            data['judgment_events'] = []
            self.assertEqual(recover_rows(data)[1],[])

    def test_pixel_source_contract_and_frame_alignment_are_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); data, frames = pixel_play(directory)
            data['game_roi'][2] += 1
            with self.assertRaisesRegex(ValueError,'source/geometry contract'):
                observe_processing(data,directory/'processing-features.npz')
            data['game_roi'][2] -= 1
            (directory/'frames.jsonl').write_text(''.join(json.dumps(f)+'\n' for f in frames[:-1]))
            with self.assertRaisesRegex(ValueError,'frame counts'):
                collect(data,directory,frames)

    def test_white_core_and_bloom_do_not_create_a_false_early_disappearance(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp); data,_=pixel_play(directory,'partial_flash')
            event=observe_processing(data,directory/'processing-features.npz')['notes'][0]
            self.assertEqual(event['status'],'unresolved')
            self.assertNotIn('range',event)
            data['visual_channels']={'processing':{'notes':[event]}}
            data['matches']=[{'note':0,'observation_lower_seconds':1.1,'observation_upper_seconds':1.12,'processing_conflict':True}]
            self.assertNotIn('processing_conflict',annotate_matches(data)['matches'][0])
            self.assertTrue(any(s['unknown_reason']=='white_effect' for s in event['samples'] if s['time']>=1))
            self.assertFalse(any(s['state']=='absent' for s in event['samples'] if 1<=s['time']<1.08))
