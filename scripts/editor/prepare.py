"""Install the lockfile adapter and an environment-aware QG hook, preserving custom hooks."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
binary = root / 'node_modules/.bin/piu-pnpm-lock-check'
binary.parent.mkdir(parents=True, exist_ok=True)
if not binary.is_symlink():
    if binary.exists():
        raise SystemExit('Refusing to replace an unrelated lockfile-check executable')
    binary.symlink_to('../../scripts/editor/piu-pnpm-lock-check')
hook_path = Path(subprocess.check_output(['git', 'rev-parse', '--git-path', 'hooks/pre-commit'], cwd=root, text=True).strip())
if not hook_path.is_absolute():
    hook_path = root / hook_path
text = hook_path.read_text() if hook_path.exists() else ''
managed = '# Installed by qg hooks install.'
command = "exec node './node_modules/@slop-lab/qg/dist/index.mjs' run-hook pre-commit"
if not text or managed in text:
    subprocess.run(['qg', 'hooks', 'install'], cwd=root, check=True)
    text = hook_path.read_text()
    if managed in text and command in text:
        text = text.replace(managed, '# Project QG hook; execute with the project environment.')
        text = text.replace(command, "exec sh scripts/run.sh node './node_modules/@slop-lab/qg/dist/index.mjs' run-hook pre-commit")
        hook_path.write_text(text)
