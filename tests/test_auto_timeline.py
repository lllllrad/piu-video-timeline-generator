"""Offline automatic orchestration and decoded-boundary tests."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("auto_timeline", ROOT / "scripts/auto_timeline.py")
auto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auto)
sys.path.pop(0)


class AutoTest(unittest.TestCase):
    def test_alternate_hud_discovery_reaches_beyond_first_ten_minutes(self):
        record = {"duration_seconds": 1200}
        initial = {"hud": (180, 0, 70, 20), "detection": {"candidates": [
            {"start_seconds": 0, "end_seconds": 1000}]}}
        def capture(record, path, seconds, roi):
            return {"file": str(path), "playback_seconds": seconds}
        recognized = [{"lines": [{"text": "STAGE", "box": [.47, .01, .05, .2]}]}]
        additional = {"candidates": [{"start_seconds": 1000, "end_seconds": 1200}]}
        with patch.object(auto, "capture_game", side_effect=capture) as frames, \
             patch.object(auto, "ocr_images", return_value=recognized), \
             patch.object(auto, "detect", return_value=additional) as detect, \
             patch.object(auto, "write_json"):
            profiles = auto.discover_profiles(record, (0, 0, 1300, 730), Path("unused"), initial)
        self.assertEqual(len(profiles), 2)
        self.assertEqual(frames.call_args.args[2], 1020)
        self.assertEqual(frames.call_args.args[3], (0, 0, 1300, 88))
        detect.assert_called_once()

    def test_merge_profiles_deduplicates_and_preserves_reference(self):
        def profile(start, end, score):
            return {"detection": {"candidates": [{"start_seconds": start, "end_seconds": end,
                                                 "mean_match_score": score}]}}
        merged = auto.merge_profile_candidates([profile(10, 30, .95), profile(12, 30, .96), profile(40, 60, .94)])
        self.assertEqual([item["profile_index"] for item in merged], [1, 2])
        with self.assertRaises(ValueError):
            auto.merge_profile_candidates([profile(10, 30, .95), profile(20, 60, .96)])

    def test_local_source_never_uses_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            video = Path(temporary) / "local.mp4"
            video.write_bytes(b"local")
            with patch.object(auto.subprocess, "run") as invoke:
                path, provenance = auto.resolve_source(str(video))
            invoke.assert_not_called()
            self.assertEqual(path, video.resolve())
            self.assertFalse(provenance["network_used"])

    def test_url_download_path_is_checked(self):
        with patch.object(auto.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "PIU_FILE:/outside.mp4\n", "")):
            with self.assertRaises(ValueError):
                auto.resolve_source("https://www.youtube.com/watch?v=_OE47GBOvB0")

    def test_corrupt_or_missing_inputs_do_not_create_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with self.assertRaises(FileNotFoundError):
                auto.run(directory / "missing.mp4", directory / "output")
            self.assertFalse((directory / "output").exists())

    def test_decode_refinement_and_no_transition(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            video = directory / "input.mp4"
            subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=2",
                "-f", "lavfi", "-i", "smptebars=s=64x64:r=10:d=4",
                "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=2",
                "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]",
                "-c:v", "mpeg4", str(video),
            ], check=True)
            record = auto.media_record(video)
            roi = (0, 0, 64, 64)
            reference = auto.reference_patch(record, roi, 3)
            start, evidence = auto.refine_boundary(record, roi, reference, 2.3, "start", radius=1)
            self.assertAlmostEqual(start, 2, places=1)
            self.assertTrue(evidence["refined"])
            end, evidence = auto.refine_boundary(record, roi, reference, 6.3, "end", radius=1)
            self.assertAlmostEqual(end, 6, places=1)
            self.assertTrue(evidence["refined"])
            unchanged, evidence = auto.refine_boundary(record, roi, reference, 4, "start", radius=.5)
            self.assertEqual(unchanged, 4)
            self.assertFalse(evidence["refined"])


if __name__ == "__main__":
    unittest.main()
