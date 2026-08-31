import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline import workflow


class WorkflowTest(unittest.TestCase):
    def test_default_node_format(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "analysis.json"
            source.write_text(json.dumps({"method": "automatic_hud_ocr", "segments": [
                {"start_seconds": 83.9, "end_seconds": 225.2, "song": "Song", "chart": "D20"}
            ]}))
            output = workflow.run_formatter(workflow.BUILTIN_FORMATS / "default/index.ts", source)
            self.assertEqual(output, "00:00 auto-generated timeline started\n01:23 Song D20 start\n03:45 Song D20 end\n")

    def test_source_ids(self):
        self.assertEqual(workflow.source_id("https://youtu.be/abc123XYZ00"), "abc123XYZ00")
        self.assertEqual(workflow.source_id("https://www.youtube.com/watch?v=abc123XYZ00&t=4"), "abc123XYZ00")
        self.assertEqual(workflow.source_id("https://www.youtube.com/live/abc123XYZ00"), "abc123XYZ00")
        self.assertEqual(workflow.source_id("https://www.youtube.com/shorts/abc123XYZ00"), "abc123XYZ00")
        self.assertEqual(workflow.source_id("https://www.youtube.com/embed/abc123XYZ00"), "abc123XYZ00")
        with tempfile.TemporaryDirectory() as temporary:
            video = Path(temporary) / "My recording.mp4"
            video.write_bytes(b"video")
            self.assertRegex(workflow.source_id(str(video)), r"^My-recording-[0-9a-f]{8}$")

    def test_format_resolution_prefers_local(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            built_in = root / "formats/default/index.ts"
            local = root / ".local/formats/default/index.ts"
            built_in.parent.mkdir(parents=True)
            built_in.write_text("built in")
            with patch.object(workflow, "BUILTIN_FORMATS", root / "formats"), \
                 patch.object(workflow, "LOCAL_FORMATS", root / ".local/formats"):
                self.assertEqual(workflow.formatter("default"), built_in)
                local.parent.mkdir(parents=True)
                local.write_text("local")
                self.assertEqual(workflow.formatter("default"), local)
                with self.assertRaises(ValueError):
                    workflow.formatter("../bad")

    def test_auto_reuses_analysis_and_writes_named_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "source.mp4"
            video.write_bytes(b"video")
            script = root / "formats/default/index.ts"
            script.parent.mkdir(parents=True)
            script.write_text("format")
            alternate = root / "formats/other/index.ts"
            alternate.parent.mkdir(parents=True)
            alternate.write_text("format")

            def fake_analyze(_video, output, _roi, _provenance):
                output.mkdir(parents=True)
                (output / "analysis.json").write_text(json.dumps({"method": "automatic_hud_ocr", "segments": []}))

            with patch.object(workflow, "LOCAL_DATA", root / "data"), \
                 patch.object(workflow, "BUILTIN_FORMATS", root / "formats"), \
                 patch.object(workflow, "LOCAL_FORMATS", root / "local-formats"), \
                 patch.object(workflow, "resolve_source", return_value=(video, {"kind": "local"})) as resolve, \
                 patch.object(workflow, "analyze", side_effect=fake_analyze) as analyze, \
                 patch.object(workflow, "run_formatter", return_value="timeline\n"):
                output = workflow.run(str(video))
                self.assertEqual(output.read_text(), "timeline\n")
                self.assertTrue(next((output.parents[1] / "raw").iterdir()).is_symlink())
                resolve.assert_called_once()
                analyze.assert_called_once()
                self.assertEqual(workflow.run(str(video), "other").read_text(), "timeline\n")
                resolve.assert_called_once()
                analyze.assert_called_once()
                self.assertEqual(workflow.run(str(video)).read_text(), "timeline\n")
                resolve.assert_called_once()
                analyze.assert_called_once()

    def test_auto_uses_cached_youtube_video_without_downloading(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            identifier = "abc123XYZ00"
            raw = root / "data" / identifier / "raw"
            raw.mkdir(parents=True)
            video = raw / f"{identifier}.mkv"
            video.write_bytes(b"video")
            script = root / "formats/default/index.ts"
            script.parent.mkdir(parents=True)
            script.write_text("format")

            def fake_analyze(source, output, _roi, provenance):
                self.assertEqual(source, video.resolve())
                self.assertEqual(provenance["kind"], "cached_youtube")
                output.mkdir(parents=True)
                (output / "analysis.json").write_text(json.dumps({"method": "automatic_hud_ocr", "segments": []}))

            with patch.object(workflow, "LOCAL_DATA", root / "data"), \
                 patch.object(workflow, "BUILTIN_FORMATS", root / "formats"), \
                 patch.object(workflow, "LOCAL_FORMATS", root / "local-formats"), \
                 patch.object(workflow, "analyze", side_effect=fake_analyze), \
                 patch.object(workflow, "run_formatter", return_value="timeline\n"), \
                 patch("piu_timeline.auto_timeline.subprocess.run") as download:
                workflow.run(identifier)
            download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
