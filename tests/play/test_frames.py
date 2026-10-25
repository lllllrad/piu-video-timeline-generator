from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import numpy as np

from piu_timeline.play.frames import decode_frames, crop_region
from piu_timeline.tools.timeline import media_record


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg tools unavailable')
class NativeFrameTest(unittest.TestCase):
    def test_native_pts_and_nonzero_origin_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            video = Path(temporary) / 'offset.mkv'
            subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-f', 'lavfi', '-i',
                            'testsrc2=s=64x64:r=20:d=0.3', '-c:v', 'ffv1',
                            '-output_ts_offset', '5', str(video)], check=True, capture_output=True)
            record = media_record(video)
            before = video.read_bytes(), video.stat().st_mtime_ns
            frames = list(decode_frames(record, .05, .25, (0, 0, 64, 64), width=32))
            self.assertGreaterEqual(len(frames), 3)
            self.assertTrue(all(pts >= 5 for pts, _, _ in frames))
            for pts, playback, image in frames:
                self.assertAlmostEqual(playback, pts - record['container_start_seconds'])
                self.assertEqual(image.shape, (32, 32, 3))
            region=(.22,.17,.35,.41)
            crops=list(decode_frames(record,.05,.25,(0,0,64,64),width=32,region=region))
            self.assertEqual(len(crops),len(frames))
            for (pts,t,image),(cpts,ct,crop) in zip(frames,crops):
                self.assertEqual((pts,t),(cpts,ct))
                np.testing.assert_array_equal(crop,crop_region(image,region))
            self.assertEqual((video.read_bytes(), video.stat().st_mtime_ns), before)
