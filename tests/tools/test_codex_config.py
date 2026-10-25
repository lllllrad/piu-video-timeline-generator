"""Config generation preserves user customizations and moved checkout paths."""
import importlib.util
from pathlib import Path
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("configure_codex", ROOT / "scripts/configure_codex.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class EnvironmentTest(unittest.TestCase):


    def test_generate_in_different_checkout_and_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'another "checkout"'
            target = generator.configure(root)
            original = target.read_text()
            self.assertEqual(generator.configure(root).read_text(), original)
            config = tomllib.loads(original)
            self.assertEqual(config["shell_environment_policy"]["set"]["MISE_DATA_DIR"], str(root.resolve() / ".local/mise_home/data"))
            moved = root.with_name('moved checkout')
            root.rename(moved)
            config = tomllib.loads(generator.configure(moved).read_text())
            overrides = config['shell_environment_policy']['set']
            self.assertEqual(overrides['MISE_DATA_DIR'], str(moved.resolve()/'.local/mise_home/data'))
            self.assertNotIn(str(root), overrides['PATH'])


    def test_preserve_user_customizations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = generator.configure(root)
            customized = target.read_text() + '\nmodel = "custom"\n'
            target.write_text(customized)
            with self.assertRaises(ValueError):
                generator.configure(root)
            self.assertEqual(target.read_text(), customized)
