"""Full-approach observations preserve native frames, dark gaps and reusable pixels."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from piu_timeline.play.appearance import acquire
from piu_timeline.play.note_types import observe_appearance


class AppearanceTest(unittest.TestCase):
    def fixture(self,root):
        media=root/'recording.mkv';media.write_bytes(b'original source')
        layout={'receptor_y':.2,'note_y_max':.95,
                'lanes':[{'x':.2+.1*i,'color':'blue'} for i in range(5)]}
        times=[0,1/60];ys=[140,135]
        frames=[{'playback_seconds':t,'source_pts_seconds':42+t,
                 'notes':[{'lane':2,'x':.4,'y':y/200}]} for t,y in zip(times,ys)]
        data={'media':{'path':str(media),'video_streams':[{'index':0}]},'game_roi':[0,0,325,200],
              'start_seconds':0,'end_seconds':.1,'analysis_width':325,'analysis_height':200,'layout':layout,
              'notes':[{'lane':2,'status':'estimated','points':list(zip(times,ys))}]}
        decoded=[]
        for time,y in zip(times,ys):
            rgb=np.zeros((200,325,3),dtype='uint8')
            cv2.rectangle(rgb,(116,y-14),(144,y+14),(255,255,255),-1)
            cv2.rectangle(rgb,(119,y-11),(141,y+11),(0,130,255),-1)
            decoded.append((42+time,time,rgb))
        return data,frames,decoded,media

    def test_far_approach_cap_on_black_background_is_confirmed_and_pixel_cache_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);data,frames,decoded,media=self.fixture(root)
            before=(media.read_bytes(),media.stat().st_mtime_ns)
            with patch('piu_timeline.play.appearance.decode_frames',return_value=iter(decoded)) as decode:
                path=acquire(data,root,frames)
            decode.assert_called_once()
            types=observe_appearance(data,path,[])
            self.assertEqual(types['notes'][0]['status'],'tap')
            self.assertEqual([o['source_pts_seconds'] for o in types['notes'][0]['observations']],[42,42+1/60])
            with patch('piu_timeline.play.appearance.decode_frames',side_effect=AssertionError('must reuse native pixels')):
                self.assertEqual(acquire(data,root,frames),path)
            self.assertEqual((media.read_bytes(),media.stat().st_mtime_ns),before)
            # A fitted point without the actual source detection cannot borrow a nearby head.
            changed=copy.deepcopy(data);changed['notes'][0]['points']=[(.009,138)]
            self.assertEqual(observe_appearance(changed,path,[])['notes'][0]['status'],'unknown')

    def test_mismatched_capture_does_not_replace_the_previous_pixel_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);data,frames,decoded,_=self.fixture(root)
            with patch('piu_timeline.play.appearance.decode_frames',return_value=iter(decoded)):
                path=acquire(data,root,frames)
            before=path.read_bytes();changed=copy.deepcopy(frames);changed[0]['notes'][0]['y']=.6
            wrong=[(43,0,decoded[0][2])]
            with patch('piu_timeline.play.appearance.decode_frames',return_value=iter(wrong)):
                with self.assertRaisesRegex(ValueError,'timestamps'):acquire(data,root,changed)
            self.assertEqual(path.read_bytes(),before)
