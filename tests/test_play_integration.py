from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from piu_timeline.play_analysis import analyze_play
from piu_timeline.play_frames import crop_region
from piu_timeline.play_tracking import DigitReader
from piu_timeline.timeline import media_record


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg unavailable')
class PlayIntegrationTest(unittest.TestCase):
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
