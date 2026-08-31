"""Analysis-only enrichment and offline presentation contracts."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
from piu_timeline.enrich_results import enrich
from piu_timeline import auto_timeline


class AnalysisWorkflowTest(unittest.TestCase):
    def test_analysis_explicit_no_judgments_does_not_inspect_render_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "analysis"
            with patch.object(sys, "argv", ["analyze.py", "local.mp4", str(output), "--no-judgments"]), \
                 patch.object(auto_timeline, "resolve_source", return_value=(Path("local.mp4"), {})), \
                 patch.object(auto_timeline, "needs_results", side_effect=AssertionError("No presentation dependency")), \
                 patch.object(auto_timeline, "analyze") as analyze:
                auto_timeline.main(analysis_only=True)
            analyze.assert_called_once_with(Path("local.mp4"), output, None, {}, False)

    def test_enrich_then_render_without_media_or_present_player(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "ocr.json"
            evidence.write_text("[]")
            source = root / "legacy.json"
            document = {"schema_version": 1, "method": "automatic_hud_ocr",
                        "game_roi": [0, 0, 1300, 730], "segments": [
                            {"start_seconds": 10, "end_seconds": 30, "song": "Song", "chart": "D21",
                             "ocr_evidence": str(evidence)}]}
            source.write_text(json.dumps(document))
            with patch("piu_timeline.enrich_results.render", side_effect=AssertionError("Must not render")):
                result = enrich(source, root / "enriched")
            self.assertEqual(result["artifact_type"], "video_analysis")
            self.assertEqual(result["segments"][0]["results"]["players"], {})
            self.assertEqual(json.loads(source.read_text()), document)
            self.assertFalse((root / "enriched/timeline.txt").exists())
            self.assertFalse((root / "enriched/timeline.json").exists())
            self.assertTrue(result["analysis_options"]["judgments"])
            with patch("piu_timeline.enrich_results.render", side_effect=ValueError("Presentation failed")):
                with self.assertRaisesRegex(ValueError, "Presentation failed"):
                    enrich(source, root / "failed-render", config={})
            self.assertTrue((root / "failed-render/analysis.json").is_file())
            self.assertFalse((root / "failed-render/timeline.json").exists())
            saved = root / "enriched/analysis.json"
            before = saved.read_bytes()
            for index, title in enumerate(("{timestamp} {song}", "{timestamp} Again {song}")):
                completed = subprocess.run([sys.executable, "-m", "piu_timeline.rendering",
                                            str(saved), str(root / f"render-{index}"), "--title", title],
                                           capture_output=True, text=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Again Song", (root / "render-1/timeline.txt").read_text())
            self.assertEqual(saved.read_bytes(), before)
            # The CLI default also keeps enrichment independent of rendering.
            completed = subprocess.run([sys.executable, "-m", "piu_timeline.enrich_results",
                                        str(saved), str(root / "cli-enriched")], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((root / "cli-enriched/analysis.json").is_file())
            self.assertFalse((root / "cli-enriched/timeline.txt").exists())
            completed = subprocess.run([sys.executable, "-m", "piu_timeline.enrich_results",
                                        str(saved), str(root / "cli-report"), "--render"], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((root / "cli-report/analysis.json").is_file())
            self.assertTrue((root / "cli-report/timeline.txt").is_file())
            with self.assertRaises(FileExistsError):
                enrich(source, root / "enriched")

    def test_analyze_rejects_presentation_before_media_access(self):
        completed = subprocess.run([sys.executable, "-m", "piu_timeline.analyze",
                                    "not-a-video", "unused", "--title", "{song}"], capture_output=True, text=True)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
