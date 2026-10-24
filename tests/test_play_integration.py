from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from piu_timeline.play_analysis import analyze_play
from piu_timeline.play_frames import crop_region, decode_frames
from piu_timeline.play_holds import augment_holds, presentation
from piu_timeline.play_tracking import DigitReader
from piu_timeline.play_judgments import augment_judgments, feature_map
from piu_timeline.timeline import media_record


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg unavailable')
class PlayIntegrationTest(unittest.TestCase):
    def test_native_long_note_is_one_sustained_state_and_replays_without_decoding(self):
        layout = {'receptor_y': .15, 'note_y_max': .95,
                  'lanes': [{'x': .38+.06*i, 'color': 'blue'} for i in range(5)]}
        def frame(time):
            image = np.zeros((183, 325, 3), dtype='uint8')
            spacing, receptor, x = 19.5, .15*183, round(.5*325)
            top = max(receptor+.3*spacing, receptor+200*(.6-time)-.45*spacing)
            bottom = min(.95*183-1, receptor+200*(1.6-time)+.45*spacing)
            if bottom > top:
                cv2.rectangle(image, (x-5, round(top)), (x+5, round(bottom)), (0,130,255), -1)
            if .6 <= time <= 1.6:
                cv2.rectangle(image, (x-5, round(receptor)-5), (x+5, round(receptor)+5), (255,255,255), -1)
            return image
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);video = root/'long.mkv'
            subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-f','rawvideo','-pixel_format','rgb24',
                            '-video_size','325x183','-framerate','60','-i','pipe:0','-c:v','ffv1',str(video)],
                           input=b''.join(frame(i/60).tobytes() for i in range(132)), check=True, capture_output=True)
            record = media_record(video);before = video.read_bytes(), video.stat().st_mtime_ns
            frames = [{'source_pts_seconds': pts, 'playback_seconds': time}
                      for pts,time,_ in decode_frames(record,0,2.2,[0,0,325,183],325)]
            (root/'frames.jsonl').write_text(''.join(json.dumps(item)+'\n' for item in frames))
            data = {'media':record,'layout':layout,'game_roi':[0,0,325,183], 'start_seconds':0,'end_seconds':2.2,
                    'analysis_width':325, 'notes':[{'lane':2,'status':'estimated','target_seconds':target,
                    'prediction_uncertainty_seconds':.01} for target in (.6,1.6)], 'matches':[{'note':0},{'note':1}]}
            result = augment_holds(data,root)
            holds = result['hold_analysis']['holds']
            self.assertEqual(len(holds),1,holds)
            self.assertAlmostEqual(sum(holds[0]['end_range'])/2,1.6,delta=.1)
            self.assertIsNone(holds[0]['input']['press_range'])
            self.assertIsNone(holds[0]['input']['release_range'])
            self.assertTrue(holds[0]['input']['segments'])
            self.assertEqual(presentation(result)['matches'],[])
            observed = [json.loads(line) for line in (root/'hold-frames.jsonl').read_text().splitlines()]
            self.assertEqual([item['source_pts_seconds'] for item in observed], [item['source_pts_seconds'] for item in frames])
            with patch('piu_timeline.play_holds.decode_frames',side_effect=AssertionError('must use cached hold pixels')):
                self.assertEqual(augment_holds(data,root)['hold_analysis'],result['hold_analysis'])
            self.assertEqual((video.read_bytes(),video.stat().st_mtime_ns),before)

    def test_first_three_inputs_match_judgments_with_no_combo_anywhere(self):
        layout={'lanes':[{'x':.1+.2*i,'color':('blue','red','yellow','red','blue')[i]} for i in range(5)],
                'receptor_y':.2,'note_y_max':.95,'combo_roi':[.4,.6,.24,.2],
                'judgment_roi':[.25,.43,.65,.2]}
        targets=(.8,1.2,1.6);labels=('PERFECT','GREAT','BAD')
        colors=((0,230,255),(30,255,70),(220,0,255))
        models=[]
        for label,color in zip(labels,colors):
            crop=np.zeros((36,208,3),dtype='uint8')
            text_width=cv2.getTextSize(label,cv2.FONT_HERSHEY_SIMPLEX,.6,2)[0][0]
            cv2.putText(crop,label,((208-text_width)//2,24),cv2.FONT_HERSHEY_SIMPLEX,.6,color,2)
            feature=feature_map(crop);ys,xs=np.nonzero(feature<18)
            models.append({'label':label,'hue':int(np.median(feature[ys,xs])),
                           'mask':(feature[ys.min():ys.max()+1,xs.min():xs.max()+1]<18).astype('uint8').tolist()})
        def frame(t):
            image=np.zeros((180,320,3),dtype='uint8')
            for target in targets:
                y=round(36+250*(target-t))
                if 10<y<205:
                    cv2.rectangle(image,(8,y-24),(56,y+24),(255,255,255),-1)
                    cv2.rectangle(image,(12,y-20),(52,y+20),(0,200,255),-1)
            active=[i for i,target in enumerate(targets) if t>=target]
            if active:
                i=active[-1];width=cv2.getTextSize(labels[i],cv2.FONT_HERSHEY_SIMPLEX,.6,2)[0][0]
                cv2.putText(image,labels[i],(80+(208-width)//2,101),cv2.FONT_HERSHEY_SIMPLEX,.6,colors[i],2)
            return image
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);video=root/'counter-free.mkv'
            subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-f','rawvideo','-pixel_format','rgb24',
                            '-video_size','320x180','-framerate','60','-i','pipe:0','-c:v','ffv1',str(video)],
                           input=b''.join(frame(i/60).tobytes() for i in range(120)),check=True,capture_output=True)
            record=media_record(video);before=video.read_bytes(),video.stat().st_mtime_ns
            with patch('piu_timeline.play_analysis.bootstrap_digits',return_value=(DigitReader(),{'ocr_images':0,'missing_digits':list('0123456789')})):
                data=analyze_play({'media':record,'game_roi':[0,0,320,180]},
                                  {'start_seconds':0,'end_seconds':2},root/'out',layout=layout,width=320)
            self.assertEqual(data['matches'],[])
            with patch('piu_timeline.play_judgments.learn_models',return_value=models), \
                    patch('piu_timeline.play_judgments.ocr_images',side_effect=AssertionError('no per-frame OCR')):
                data=augment_judgments(data,root/'out')
            self.assertEqual(len(data['matches']),3,data['judgment_events'])
            self.assertEqual([m['judgment_label'] for m in data['matches']],list(labels))
            self.assertTrue(all(m['combo_event'] is None for m in data['matches']))
            for match,target in zip(data['matches'],targets):
                self.assertAlmostEqual(match['target_seconds'],target,delta=.03)
            self.assertEqual((video.read_bytes(),video.stat().st_mtime_ns),before)

    def test_synthetic_note_combo_delay_and_source_integrity(self):
        layout = {'lanes': [{'x': .1 + .2*i, 'color': ('blue','red','yellow','red','blue')[i], 'name': str(i)} for i in range(5)],
                  'receptor_y': .2, 'note_y_max': .95, 'combo_roi': [.40, .60, .24, .20]}
        def frame(t):
            image = np.zeros((180, 320, 3), dtype='uint8')
            y = round(236 - 250*t)
            if y > 20:
                cv2.rectangle(image, (8, y-24), (56,y+24), (255,255,255), -1)
                cv2.rectangle(image, (12, y-20), (52,y+20), (0,200,255), -1)
            value = 10 if t < .84 else 11
            cv2.putText(image,str(value),(137,135),cv2.FONT_HERSHEY_SIMPLEX,.8,(255,255,255),2)
            return image
        def bootstrap(*args, **kwargs):
            reader=DigitReader()
            for t in (.1,.2,1.1,1.2):
                reader.train(crop_region(frame(t), layout['combo_roi']), 10 if t < .84 else 11)
            return reader, {'ocr_images':0,'missing_digits':[],'template_counts':{}}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);video=root/'synthetic.mkv'
            raw=b''.join(frame(i/30).tobytes() for i in range(60))
            subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-f','rawvideo','-pixel_format','rgb24',
                            '-video_size','320x180','-framerate','30','-i','pipe:0','-c:v','ffv1',str(video)],
                           input=raw,check=True,capture_output=True)
            record=media_record(video);before=(video.stat().st_size,video.stat().st_mtime_ns)
            with patch('piu_timeline.play_analysis.bootstrap_digits',side_effect=bootstrap):
                data=analyze_play({'media':record,'game_roi':[0,0,320,180]},
                                  {'start_seconds':0,'end_seconds':2,'chart':'S1'},root/'out',layout=layout,width=320)
            self.assertEqual(data['frame_count'],60)
            self.assertGreater(len(data['matches']),0, (data['combo_readable_fraction'],data['combo_events'],[(n['status'],n.get('reason'),n.get('target_seconds'),n['points']) for n in data['notes']]))
            match=data['matches'][0]
            self.assertAlmostEqual(match['target_seconds'],.8,delta=.03)
            self.assertGreater(match['raw_offset_upper_ms'],0)
            self.assertEqual((video.stat().st_size,video.stat().st_mtime_ns),before)
