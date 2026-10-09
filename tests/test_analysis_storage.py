import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline import workflow


class StorageTest(unittest.TestCase):
    def test_promoted_nested_evidence_paths_are_valid(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pending, final = root / "analysis.build", root / "analysis"
            pending.mkdir()
            image = pending / "frame.png"
            image.write_bytes(b"pixels")
            source = root / "original.mp4"
            source.write_bytes(b"source")
            data = {"file": str(image), "nested": [{"image": str(image)}], "media": str(source)}
            (pending / "analysis.json").write_text(json.dumps(data))
            workflow.relocate_evidence(pending, final)
            pending.rename(final)
            result = json.loads((final / "analysis.json").read_text())
            self.assertTrue(Path(result["file"]).is_file())
            self.assertEqual(result["nested"][0]["image"], str(final / "frame.png"))
            self.assertEqual(result["media"], str(source))

    def test_failed_rebuild_keeps_old_analysis_and_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "data/abc123XYZ00"
            old = directory / "analysis/analysis.json"
            old.parent.mkdir(parents=True)
            old.write_text(json.dumps({"analysis_version": 0}))
            text = directory / "output/default.txt"
            text.parent.mkdir()
            text.write_text("previous\n")
            raw = directory / "raw/source.mp4"
            raw.parent.mkdir()
            raw.write_bytes(b"source")
            with patch.object(workflow, "LOCAL_DATA", root / "data"), \
                 patch.object(workflow, "formatter", return_value=Path("unused.ts")), \
                 patch.object(workflow, "analyze", side_effect=ValueError("OCR failed")):
                with self.assertRaisesRegex(ValueError, "OCR failed"):
                    workflow.run("abc123XYZ00")
            self.assertEqual(json.loads(old.read_text())["analysis_version"], 0)
            self.assertEqual(text.read_text(), "previous\n")
            self.assertEqual(raw.read_bytes(), b"source")

    def test_explicit_roi_or_backend_change_invalidates_cache(self):
        for change in ("roi", "backend"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                old = root / "data/abc123XYZ00/analysis/analysis.json"
                old.parent.mkdir(parents=True)
                document = {"analysis_version": workflow.ANALYSIS_VERSION, "game_roi": [0, 0, 1300, 730],
                            "ocr_configuration": workflow.configuration()}
                if change == "backend":
                    document["ocr_configuration"] = {"backend": "different"}
                old.write_text(json.dumps(document))
                with patch.object(workflow, "LOCAL_DATA", root / "data"), \
                     patch.object(workflow, "formatter", return_value=Path("unused.ts")), \
                     patch.object(workflow, "resolve_source", side_effect=ValueError("rebuild requested")):
                    with self.assertRaisesRegex(ValueError, "rebuild requested"):
                        workflow.run("abc123XYZ00", game_roi=(0, 0, 1920, 1080) if change == "roi" else None)
