"""Offline checks for the checkout-specific Codex environment and just recipes."""
import json
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("configure_codex", ROOT / "scripts/configure_codex.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class EnvironmentTest(unittest.TestCase):
    def test_codex_environment_resolves_local_just(self):
        config = tomllib.loads(generator.render(ROOT))
        self.assertFalse(config["allow_login_shell"])
        overrides = config["shell_environment_policy"]["set"]
        env = overrides
        result = subprocess.run(
            ["/bin/sh", "-c", "command -v just && just --version"],
            cwd=ROOT, env=env, check=True, capture_output=True, text=True,
        )
        self.assertEqual(result.stdout.splitlines()[0], str(ROOT / ".local/mise_home/data/shims/just"))
        self.assertIn("just 1.58.0", result.stdout)
        local = str(ROOT / ".local")
        self.assertEqual(overrides["MISE_DATA_DIR"], f"{local}/mise_home/data")
        self.assertEqual(overrides["MISE_CACHE_DIR"], f"{local}/mise_home/cache")
        self.assertEqual(overrides["MISE_STATE_DIR"], f"{local}/mise_home/state")
        self.assertEqual(overrides["XDG_CACHE_HOME"], f"{local}/cache")
        self.assertEqual(overrides["PIP_CACHE_DIR"], f"{local}/cache/pip")
        self.assertNotIn("DENO_DIR", overrides)

    def test_public_auto_help(self):
        result = subprocess.run(
            ["just", "auto", "--help"], cwd=ROOT,
            check=True, capture_output=True, text=True,
        )
        self.assertIn("Local video, YouTube URL", result.stdout)
        self.assertIn("--game-roi", result.stdout)

    def test_public_fetch_help(self):
        result = subprocess.run(
            ["just", "fetch", "--help"], cwd=ROOT,
            check=True, capture_output=True, text=True,
        )
        self.assertIn("YouTube URL or 11-character video ID", result.stdout)

    def test_just_probe_preserves_path_arguments(self):
        with tempfile.TemporaryDirectory() as temporary:
            video = Path(temporary) / "studio's video; literal.mp4"
            subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                "color=c=black:s=64x64:r=10", "-t", "1", "-c:v", "mpeg4", str(video)
            ], check=True)
            result = subprocess.run(
                ["just", "_probe", str(video)], cwd=ROOT,
                check=True, capture_output=True, text=True,
            )
            self.assertEqual(json.loads(result.stdout)["format"]["filename"], str(video))

    def test_generate_in_different_checkout_and_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'another "checkout"'
            target = generator.configure(root)
            original = target.read_text()
            self.assertEqual(generator.configure(root).read_text(), original)
            config = tomllib.loads(original)
            self.assertEqual(config["shell_environment_policy"]["set"]["MISE_DATA_DIR"], str(root.resolve() / ".local/mise_home/data"))

    def test_regenerate_after_move(self):
        with tempfile.TemporaryDirectory() as directory:
            before, after = Path(directory) / "before", Path(directory) / "after"
            generator.configure(before)
            before.rename(after)
            self.assertEqual(generator.configure(after).read_text(), generator.render(after))

    def test_preserve_user_customizations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = generator.configure(root)
            customized = target.read_text() + '\nmodel = "custom"\n'
            target.write_text(customized)
            with self.assertRaises(ValueError):
                generator.configure(root)
            self.assertEqual(target.read_text(), customized)
