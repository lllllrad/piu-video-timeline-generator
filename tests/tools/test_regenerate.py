"""Batch regeneration must retain reports when individual sources fail."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "regenerate", Path(__file__).resolve().parents[2] / "scripts/regenerate.py")
regenerate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(regenerate)


class RegenerationTests(unittest.TestCase):
    def test_source_failure_does_not_interrupt_remaining_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for source in ("abcdefghijk", "lmnopqrstuv"):
                raw = root / ".local/data" / source / "raw"
                raw.mkdir(parents=True)
                (raw / "video.mp4").write_bytes(b"original")

            def execute(command, **kwargs):
                if command[-1] == "abcdefghijk":
                    raise OSError("could not launch")
                return subprocess.CompletedProcess(command, 0)

            with patch.object(regenerate, "ROOT", root), patch("sys.argv", ["regenerate", "--jobs", "1"]), \
                    patch.object(regenerate.subprocess, "run", side_effect=execute), patch("builtins.print"):
                with self.assertRaises(SystemExit) as error:
                    regenerate.main()
            self.assertEqual(error.exception.code, 1)
            report = json.loads(next(root.glob(".local/runs/regeneration-*/report.json")).read_text())
            results = {item["source"]: item for item in report}
            self.assertEqual(len(results), 2)
            self.assertIn("could not launch", results["abcdefghijk"]["error"])
            self.assertIsNone(results["abcdefghijk"]["source_unchanged"])
            self.assertEqual(results["lmnopqrstuv"]["exit_code"], 0)
            self.assertTrue(results["lmnopqrstuv"]["source_unchanged"])


if __name__ == "__main__":
    unittest.main()
