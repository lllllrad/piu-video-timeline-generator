import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("evaluate", ROOT / "scripts/evaluate.py")
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)
sys.path.pop(0)


class EvaluationTest(unittest.TestCase):
    def test_missing_identity_nonfinite_coverage_and_crossing_prediction_rejected(self):
        media = {"path": "test", "size_bytes": 1, "mtime_ns": 2}
        prediction = {"media": media, "segments": [{"start_seconds": 5, "end_seconds": 20}]}
        reference = {"media": media, "method": "independent_video_review", "coverage_seconds": [10, 30],
                     "segments": [{"start_range": [12, 13], "end_range": [19, 20], "evidence": "Frames"}]}
        with self.assertRaisesRegex(ValueError, "crosses"):
            evaluation.evaluate(prediction, reference)
        reference["coverage_seconds"] = [0, float("inf")]
        with self.assertRaises(ValueError):
            evaluation.evaluate(prediction, reference)
        reference["coverage_seconds"] = [0, 30]
        prediction["media"] = reference["media"] = {}
        with self.assertRaises(ValueError):
            evaluation.evaluate(prediction, reference)

    def test_false_positive_miss_unknown_and_timing(self):
        media = {"path": "test", "size_bytes": 1, "mtime_ns": 2}
        predicted = {"media": media, "segments": [
            {"start_seconds": 10, "end_seconds": 20, "song": "곡 이름", "chart": None},
            {"start_seconds": 60, "end_seconds": 70, "song": "False", "chart": "D20"},
        ]}
        reference = {"media": media, "method": "independent_video_review", "coverage_seconds": [0, 100], "segments": [
            {"start_range": [10, 11], "end_range": [21, 22], "song": "곡이름", "chart": "D21", "evidence": "Frames"},
            {"start_range": [40, 41], "end_range": [50, 51], "song": "Missed", "chart": "D22", "evidence": "Frames"},
        ]}
        result = evaluation.evaluate(predicted, reference)
        self.assertEqual(result["missed_segments"], 1)
        self.assertEqual(result["false_positives"], 1)
        self.assertEqual(result["precision"], .5)
        self.assertEqual(result["recall"], .5)
        self.assertEqual(result["song_correct"], 1)
        self.assertEqual(result["chart_correct"], 0)
        self.assertEqual(result["matches"][0]["end_outside_review_range_seconds"], 1)
        reference["method"] = "comments"
        with self.assertRaises(ValueError):
            evaluation.evaluate(predicted, reference)


if __name__ == "__main__":
    unittest.main()
