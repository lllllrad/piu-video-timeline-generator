import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from piu_timeline import media


class MediaTest(unittest.TestCase):
    def test_video_id(self):
        self.assertEqual(media.resolve_url("_OE47GBOvB0"), "https://www.youtube.com/watch?v=_OE47GBOvB0")

    def test_url_variants(self):
        for url in ["https://m.youtube.com/watch?v=5l0xgojfQGs&ra=m", "https://www.youtube.com/live/uqM7H-OJp68?si=test"]:
            self.assertEqual(media.resolve_url(url), url)

    def test_invalid_source(self):
        for source in ["--exec=bad", "file:///tmp/video", "https://youtube.com.evil.test/video"]:
            with self.assertRaises(ValueError):
                media.resolve_url(source)

    def test_download(self):
        command = media.fetch_command("_OE47GBOvB0", Path("/tmp/raw"))
        self.assertIn("--ignore-config", command)
        self.assertIn("--no-playlist", command)
        self.assertEqual(command[command.index("--js-runtimes") + 1], "node")
        self.assertIn("!is_live", command)
        self.assertEqual(command[-2], "--")

    def test_fragment_concurrency(self):
        command = media.fetch_command("_OE47GBOvB0", Path("/tmp/raw"), concurrent_fragments=8)
        self.assertEqual(command[command.index("--concurrent-fragments") + 1], "8")
        for value in (0, 17, True, "4", 1.5):
            with self.assertRaises(ValueError):
                media.fetch_command("_OE47GBOvB0", Path("/tmp/raw"), concurrent_fragments=value)

    def test_local_video_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            video = Path(temporary) / "studio download.mp4"
            subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                "color=c=black:s=64x64:r=10", "-t", "1", "-c:v", "mpeg4", str(video)
            ], check=True)
            result = subprocess.run([
                sys.executable, "-m", "piu_timeline.media", str(video)
            ], check=True, capture_output=True, text=True)
            info = json.loads(result.stdout)
            self.assertAlmostEqual(float(info["format"]["duration"]), 1, places=1)
            self.assertEqual(info["streams"][0]["width"], 64)

    def test_missing_local_video(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run([
                sys.executable, "-m", "piu_timeline.media",
                str(Path(temporary) / "missing.mp4")
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Video not found", result.stderr)
