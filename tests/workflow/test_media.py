import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from piu_timeline import media, workflow


class MediaTest(unittest.TestCase):
    def test_video_ids_and_supported_url_forms(self):
        for source, expected in (
                ("_OE47GBOvB0", "https://www.youtube.com/watch?v=_OE47GBOvB0"),
                ("https://m.youtube.com/watch?v=5l0xgojfQGs&ra=m", "https://m.youtube.com/watch?v=5l0xgojfQGs&ra=m"),
                ("https://www.youtube.com/live/uqM7H-OJp68?si=test", "https://www.youtube.com/live/uqM7H-OJp68?si=test")):
            with self.subTest(source=source):
                self.assertEqual(media.resolve_url(source), expected)

    def test_invalid_source(self):
        for source in ["--exec=bad", "file:///tmp/video", "https://youtube.com.evil.test/video"]:
            with self.assertRaises(ValueError):
                media.resolve_url(source)

    def test_download(self):
        command = media.fetch_command("_OE47GBOvB0", Path("/tmp/raw"))
        self.assertIn("--ignore-config", command)
        self.assertIn("--no-playlist", command)
        self.assertIn("--progress", command)
        self.assertIn("--newline", command)
        self.assertIn("--no-quiet", command)
        self.assertEqual(command[command.index("--js-runtimes") + 1], "node")
        self.assertIn("!is_live", command)
        self.assertEqual(command[-2], "--")

    def test_download_progress_is_forwarded_before_completion(self):
        messages = io.StringIO()
        def lines():
            yield "[download] 10% ETA 00:45\n"
            # The process has not emitted its final path or exited yet.
            self.assertIn("10% ETA 00:45", messages.getvalue())
            yield "[download] 100%\n"
            yield "PIU_FILE:/tmp/completed video.mkv\n"
        with patch.object(media.subprocess, "Popen") as popen, redirect_stderr(messages):
            process = popen.return_value.__enter__.return_value
            process.stdout = lines()
            process.wait.return_value = 0
            output = media.run_download(["yt-dlp"])
        self.assertEqual(output, "PIU_FILE:/tmp/completed video.mkv\n")
        self.assertIn("100%", messages.getvalue())
        self.assertNotIn("PIU_FILE:", messages.getvalue())

    def test_download_error_stays_visible_and_fails(self):
        messages = io.StringIO()
        with redirect_stderr(messages), self.assertRaises(subprocess.CalledProcessError) as raised:
            media.run_download([sys.executable, "-c", "import sys; print('ERROR: unavailable', file=sys.stderr); sys.exit(7)"])
        self.assertEqual(raised.exception.returncode, 7)
        self.assertIn("ERROR: unavailable", messages.getvalue())
        self.assertIn("ERROR: unavailable", raised.exception.stderr)

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

    def test_just_probe_preserves_path_arguments(self):
        with tempfile.TemporaryDirectory() as temporary:
            video = Path(temporary) / "studio's video; literal.mp4"
            subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                "color=c=black:s=64x64:r=10", "-t", "1", "-c:v", "mpeg4", str(video)
            ], check=True)
            result = subprocess.run(
                ["just", "_probe", str(video)], cwd=workflow.ROOT,
                check=True, capture_output=True, text=True,
            )
            self.assertEqual(json.loads(result.stdout)["format"]["filename"], str(video))
