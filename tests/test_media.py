import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("media", Path(__file__).resolve().parents[1] / "scripts/media.py")
media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)


class MediaTest(unittest.TestCase):
    def test_seed(self):
        self.assertEqual(media.resolve_url("_OE47GBOvB0"), "https://www.youtube.com/watch?v=_OE47GBOvB0")

    def test_url_variants(self):
        for url in ["https://m.youtube.com/watch?v=5l0xgojfQGs&ra=m", "https://www.youtube.com/live/uqM7H-OJp68?si=test"]:
            self.assertEqual(media.resolve_url(url), url)

    def test_invalid_source(self):
        for source in ["--exec=bad", "file:///tmp/video", "https://youtube.com.evil.test/video"]:
            with self.assertRaises(ValueError):
                media.resolve_url(source)

    def test_download_without_labels(self):
        command = media.fetch_command("_OE47GBOvB0")
        self.assertNotIn("--write-comments", command)
        self.assertIn("--ignore-config", command)
        self.assertIn("--no-playlist", command)
        self.assertIn("!is_live", command)
        self.assertEqual(command[-2], "--")

    def test_metadata_only(self):
        self.assertIn("--skip-download", media.fetch_command("_OE47GBOvB0", metadata_only=True))

    def test_labels_are_separate(self):
        command = media.fetch_command("5l0xgojfQGs", comments=True)
        self.assertIn("--skip-download", command)
        self.assertIn("--write-comments", command)
        self.assertIn(str(media.ROOT / "data/labels"), command)

    def test_local_video_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            video = Path(temporary) / "studio download.mp4"
            subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                "color=c=black:s=64x64:r=10", "-t", "1", "-c:v", "mpeg4", str(video)
            ], check=True)
            result = subprocess.run([
                sys.executable, str(media.ROOT / "scripts/media.py"), "probe", str(video)
            ], check=True, capture_output=True, text=True)
            info = json.loads(result.stdout)
            self.assertAlmostEqual(float(info["format"]["duration"]), 1, places=1)
            self.assertEqual(info["streams"][0]["width"], 64)

    def test_missing_local_video(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run([
                sys.executable, str(media.ROOT / "scripts/media.py"),
                "probe", str(Path(temporary) / "missing.mp4")
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Video not found", result.stderr)
