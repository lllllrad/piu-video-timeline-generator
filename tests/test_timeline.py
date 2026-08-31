"""Offline timeline validation and real FFmpeg/CLI integration checks."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
from piu_timeline import timeline


class TimelineTest(unittest.TestCase):
    def setUp(self):
        self.record = {
            "path": "/example/video.mp4", "size_bytes": 123, "mtime_ns": 456,
            "duration_seconds": 4000, "container_start_seconds": 12.5,
            "timestamp_basis": "seconds_from_local_playback_start", "video_streams": [],
        }
        self.review = timeline.review_template(self.record)
        self.review["segments"] = [self.segment(59.9, 120), self.segment(3601.25, 3700)]

    @staticmethod
    def segment(start, end):
        return {"start_seconds": start, "end_seconds": end, "song": "한글 Song",
                "chart": "D20", "confidence": 0.8, "evidence": "Direct video review of gameplay"}

    def build(self):
        return timeline.build_timeline(self.review, self.record)

    def test_fractional_times_and_hours(self):
        result = self.build()
        self.assertEqual(result["segments"][0]["start_seconds"], 59.9)
        self.assertEqual(result["media"]["container_start_seconds"], 12.5)
        self.assertEqual(timeline.render_text(result),
                         "00:00 auto-generated timeline started\n00:59 한글 Song D20 start\n02:00 한글 Song D20 end\n"
                         "1:00:01 한글 Song D20 start\n1:01:40 한글 Song D20 end\n")
        for seconds, expected in [(0, "00:00"), (60, "01:00"), (3599.99, "59:59"), (3600, "1:00:00")]:
            self.assertEqual(timeline.timestamp(seconds), expected)

    def test_unknowns_and_empty_timeline(self):
        self.review["segments"] = [{**self.segment(0, 1), "song": None, "chart": None, "confidence": None}]
        self.assertEqual(timeline.render_text(self.build()),
                         "00:00 auto-generated timeline started\n00:00 Unknown song start\n00:01 Unknown song end\n")
        self.review["segments"] = []
        self.assertEqual(timeline.render_text(self.build()), "00:00 auto-generated timeline started\n")

    def test_alignment_is_explicit_and_preserves_local_times(self):
        with self.assertRaises(ValueError):
            timeline.render_text(self.build(), youtube=True)
        self.review["alignment"] = {"youtube_url": "https://www.youtube.com/watch?v=_OE47GBOvB0", "offset_seconds": 10}
        result = self.build()
        self.assertEqual(result["segments"][0]["start_seconds"], 59.9)
        self.assertEqual(result["segments"][0]["youtube_start_seconds"], 69.9)
        self.assertIn("01:09 한글 Song D20 start", timeline.render_text(result, youtube=True))

    def test_bad_alignment(self):
        for alignment in [None, {"youtube_url": "url"}, {"offset_seconds": 0},
                          {"youtube_url": "url", "offset_seconds": -60},
                          {"youtube_url": "url", "offset_seconds": float("nan")}]:
            with self.subTest(alignment=alignment), self.assertRaises(ValueError):
                self.review["alignment"] = alignment
                self.build()

    def test_invalid_numbers(self):
        for key in ("start_seconds", "end_seconds", "confidence"):
            for value in [True, "12", float("nan"), float("inf"), -1]:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.review["segments"] = [{**self.segment(0, 2), key: value}]
                    self.build()
        self.review["segments"] = [{**self.segment(0, 2), "confidence": 1.1}]
        with self.assertRaises(ValueError):
            self.build()

    def test_invalid_intervals(self):
        for intervals in [[(2, 2)], [(3, 2)], [(0, 4001)], [(0, 10), (9, 20)], [(20, 30), (0, 10)]]:
            with self.subTest(intervals=intervals), self.assertRaises(ValueError):
                self.review["segments"] = [self.segment(*pair) for pair in intervals]
                self.build()
        self.review["segments"] = [self.segment(0, 10), self.segment(10, 20)]
        self.build()

    def test_bad_text_and_missing_evidence(self):
        for key in ("song", "chart", "evidence"):
            for value in ["", "line\nbreak", "line\u2028break", 123, "  "]:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.review["segments"] = [{**self.segment(0, 2), key: value}]
                    self.build()
        self.review["segments"] = [{**self.segment(0, 2), "evidence": None}]
        with self.assertRaises(ValueError):
            self.build()

    def test_wrong_source_or_schema(self):
        for key, value in [("schema_version", 2), ("schema_version", True), ("method", "wrong_method"), ("media", {}),
                           ("segments", {}), ("segments", [None])]:
            review = copy.deepcopy(self.review)
            review[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                timeline.build_timeline(review, self.record)
        self.review["media"] = {**self.record, "mtime_ns": 789}
        with self.assertRaises(ValueError):
            self.build()

    def test_misspelled_segment_fields_are_rejected(self):
        self.review["segments"][0]["song_name"] = "Typo"
        with self.assertRaises(ValueError):
            self.build()

    def test_missing_corrupt_and_audio_only_media(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(FileNotFoundError):
                timeline.media_record(root / "missing.mp4")
            corrupt = root / "corrupt.mp4"
            corrupt.write_bytes(b"not a video")
            with self.assertRaises(subprocess.CalledProcessError):
                timeline.media_record(corrupt)
            audio = root / "audio.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=0.1", str(audio)], check=True)
            with self.assertRaises(ValueError):
                timeline.media_record(audio)
            partial = root / "download.part"
            partial.write_bytes(b"incomplete")
            with self.assertRaises(ValueError):
                timeline.media_record(partial)

    def test_cli_round_trip_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            video = directory / "studio's video; literal.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "color=c=black:s=64x64:r=10", "-t", "2", "-c:v", "mpeg4", str(video)], check=True)
            original = video.read_bytes()
            record = json.loads(subprocess.run(["just", "_record", str(video)], cwd=ROOT,
                                               check=True, capture_output=True, text=True).stdout)
            self.assertEqual(record["duration_seconds"], 2)
            self.assertEqual(record["video_streams"][0]["avg_frame_rate"], "10/1")
            review_path = directory / "review.json"
            result = subprocess.run(["just", "_review", str(video), str(review_path)], cwd=ROOT,
                                    check=True, capture_output=True, text=True)
            review = json.loads(review_path.read_text())
            review["segments"] = [self.segment(0.25, 1.5)]
            review_path.write_text(json.dumps(review), encoding="utf-8")
            output = directory / "results"
            command = ["just", "_timeline", str(video), str(review_path), str(output)]
            subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
            self.assertEqual((output / "timeline.txt").read_text(),
                             "00:00 auto-generated timeline started\n00:00 한글 Song D20 start\n00:01 한글 Song D20 end\n")
            result = json.loads((output / "timeline.json").read_text())
            self.assertEqual(result["segments"][0]["start_seconds"], 0.25)
            self.assertEqual(result["text_timestamp_basis"], "local_playback")
            self.assertNotEqual(subprocess.run(command, cwd=ROOT, capture_output=True).returncode, 0)
            for target in (review_path, video):
                result = subprocess.run(["just", "_review", str(video), str(target)], cwd=ROOT, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
            self.assertEqual(video.read_bytes(), original)

    def test_cli_rejects_invalid_review_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            video = directory / "video.mkv"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=64x64:r=10",
                            "-t", "1", "-output_ts_offset", "5", str(video)], check=True)
            record = timeline.media_record(video)
            self.assertEqual(record["container_start_seconds"], 5)
            self.assertAlmostEqual(record["duration_seconds"], 1)
            frames = directory / "frames"
            subprocess.run(["just", "_frames", str(video), str(frames), "--at", "0.45"],
                           cwd=ROOT, capture_output=True, check=True)
            sampled = json.loads((frames / "frames.json").read_text())["frames"][0]
            self.assertAlmostEqual(sampled["source_pts_seconds"], 5.5)
            self.assertAlmostEqual(sampled["playback_seconds"], 0.5)
            self.assertTrue((frames / sampled["file"]).read_bytes().startswith(b"\x89PNG"))
            review_path = directory / "review.json"
            review_path.write_text("not JSON")
            output = directory / "results"
            result = subprocess.run(["just", "_timeline", str(video), str(review_path), str(output)],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
