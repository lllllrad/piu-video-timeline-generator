from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from piu_timeline.play_frames import decode_frames
from piu_timeline.timeline import media_record


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg tools unavailable')
class NativeFrameTest(unittest.TestCase):
    def test_native_pts_and_nonzero_origin_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            video = Path(temporary) / 'offset.mkv'
            subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-f', 'lavfi', '-i',
                            'color=c=black:s=64x64:r=20:d=0.3', '-c:v', 'ffv1',
                            '-output_ts_offset', '5', str(video)], check=True, capture_output=True)
            record = media_record(video)
            before = video.read_bytes(), video.stat().st_mtime_ns
            frames = list(decode_frames(record, .05, .25, (0, 0, 64, 64), width=32))
            self.assertGreaterEqual(len(frames), 3)
            self.assertTrue(all(pts >= 5 for pts, _, _ in frames))
            for pts, playback, image in frames:
                self.assertAlmostEqual(playback, pts - record['container_start_seconds'])
                self.assertEqual(image.shape, (32, 32, 3))
            self.assertEqual((video.read_bytes(), video.stat().st_mtime_ns), before)
