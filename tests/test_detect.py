"""Synthetic checks for experimental candidate matching, not accuracy benchmarks."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
from piu_timeline import detect


class DetectTest(unittest.TestCase):
    def test_intervals_and_gaps(self):
        scores = [0, 1, 1, 0, 1, 0, 0, 0, 1, 1]
        result = detect.intervals(scores, 2, 19, .9, 3, 2)
        self.assertEqual([(s["start_seconds"], s["end_seconds"]) for s in result], [(2, 10), (16, 19)])
        self.assertTrue(all(s["needs_review"] and s["song"] is None for s in result))
        self.assertEqual(detect.intervals([], 2, 20, .9, 3, 2), [])
        self.assertEqual(detect.intervals([0, 0], 2, 4, .9, 3, 2), [])

    def test_similarity(self):
        self.assertEqual(detect.similarity(bytes([0, 255]), bytes([0, 255])), 1)
        self.assertEqual(detect.similarity(bytes([0, 0]), bytes([255, 255])), 0)

    def test_roi(self):
        self.assertEqual(detect.roi_value("10,20,30,40"), (10, 20, 30, 40))
        for value in ("1,2,3", "-1,0,2,2", "0,0,0,2", "a,b,c,d"):
            with self.assertRaises(argparse.ArgumentTypeError):
                detect.roi_value(value)

    def test_synthetic_video_candidates(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            video = directory / "input.mp4"
            subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=2",
                "-f", "lavfi", "-i", "smptebars=s=64x64:r=10:d=4",
                "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=2",
                "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]",
                "-c:v", "mpeg4", "-g", "10", str(video),
            ], check=True)
            output = directory / "candidates.json"
            command = ["just", "_detect", str(video), str(output), "--roi", "0,0,64,64",
                       "--reference-at", "3", "--step", "1", "--min-duration", "1", "--max-gap", "0"]
            subprocess.run(command, cwd=ROOT, capture_output=True, check=True)
            result = json.loads(output.read_text())
            self.assertEqual(len(result["candidates"]), 1)
            candidate = result["candidates"][0]
            self.assertEqual(candidate["start_seconds"], 2)
            self.assertEqual(candidate["end_seconds"], 6)
            self.assertEqual(len(result["samples"]), 8)
            with self.assertRaises(ValueError):
                detect.detect(result["media"], (0, 0, 64, 64), 0)
            with self.assertRaises(ValueError):
                detect.detect(result["media"], (0, 0, 65, 64), 3)
            self.assertNotEqual(subprocess.run(command, cwd=ROOT, capture_output=True).returncode, 0)

    def test_corrupt_input_is_a_clean_cli_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "corrupt.mp4"
            video.write_bytes(b"not video")
            result = subprocess.run(["just", "_detect", str(video), str(root / "output.json"),
                                     "--roi", "0,0,64,64", "--reference-at", "0"],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse((root / "output.json").exists())


if __name__ == "__main__":
    unittest.main()
