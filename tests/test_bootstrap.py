"""Offline coverage for first-run setup, reuse and installation recovery."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("bootstrap", Path(__file__).resolve().parents[1] / "scripts/bootstrap.py")
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class BootstrapTest(unittest.TestCase):
    def checkout(self, root):
        for name in ("pyproject.toml", "requirements.txt", "requirements-dev.txt"):
            (root / name).write_text(name)

    def create_venv(self, directory, **kwargs):
        (directory / "bin").mkdir()
        (directory / "bin/python").touch()

    def test_first_run_reuse_and_dependency_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.checkout(root)
            with patch.object(bootstrap.venv, "create", side_effect=self.create_venv) as create, \
                    patch.object(bootstrap.subprocess, "run") as install:
                bootstrap.prepare(root)
                bootstrap.prepare(root)
                create.assert_called_once_with(root / ".venv", with_pip=True)
                self.assertEqual(install.call_count, 1)
                self.assertIn("requirements-dev.txt", install.call_args.args[0])
                (root / "pyproject.toml").write_text("changed dependency")
                bootstrap.prepare(root)
                self.assertEqual(install.call_count, 2)

    def test_failed_install_retries_without_ready_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.checkout(root)
            with patch.object(bootstrap.venv, "create", side_effect=self.create_venv), \
                    patch.object(bootstrap.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "pip")):
                with self.assertRaises(subprocess.CalledProcessError):
                    bootstrap.prepare(root)
            self.assertFalse((root / ".venv/.bootstrap.json").exists())
            with patch.object(bootstrap.subprocess, "run") as install:
                bootstrap.prepare(root)
                install.assert_called_once()
