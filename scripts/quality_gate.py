"""Run the pinned upstream QG CLI until its npm package is published."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys


REVISION = '7093d0761a3c3ca5ae7070542271c8bcebfd1173'
PNPM = '11.10.0'
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.local/cache/qg'
# QG excludes node_modules when discovering nested configuration. Keep this
# tool dependency's own configuration outside the consuming project's scope.
CHECKOUT = CACHE / 'node_modules/quality-gate'
CLI = CHECKOUT / 'packages/cli/dist/index.mjs'


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    with (CACHE / 'setup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        stamp = CACHE / 'built-revision'
        if not CLI.is_file() or not stamp.is_file() or stamp.read_text().strip() != REVISION:
            print('Setting up the pinned Quality Gate checkout...', file=sys.stderr, flush=True)
            # Node's native TypeScript loader rejects configs under node_modules.
            # Build outside it, then move the complete dependency into place.
            build = CACHE / 'build'
            if CHECKOUT.exists() and not build.exists():
                CHECKOUT.rename(build)
            if not (build / '.git').is_dir():
                subprocess.run(['git', 'clone', '--no-checkout',
                                'https://github.com/slop-lab/quality-gate.git', str(build)],
                               check=True, stdout=sys.stderr)
            subprocess.run(['git', 'fetch', '--depth=1', 'origin', REVISION],
                           cwd=build, check=True, stdout=sys.stderr)
            subprocess.run(['git', 'checkout', '--detach', REVISION],
                           cwd=build, check=True, stdout=sys.stderr)
            env = {**os.environ, 'npm_config_cache': str(ROOT / '.local/cache/npm'), 'CI': 'true'}
            npm = ['npm', 'exec', '--yes', f'--package=pnpm@{PNPM}', '--']
            subprocess.run([*npm, 'pnpm', 'install', '--frozen-lockfile',
                            '--store-dir', str(ROOT / '.local/cache/pnpm-store')],
                           cwd=build, env=env, check=True, stdout=sys.stderr)
            subprocess.run([*npm, 'node', 'scripts/run-task.mjs', 'build'],
                           cwd=build, env=env, check=True, stdout=sys.stderr)
            CHECKOUT.parent.mkdir(parents=True, exist_ok=True)
            build.rename(CHECKOUT)
            stamp.write_text(REVISION + '\n')
    os.chdir(ROOT)
    os.execvp('node', ['node', str(CLI), *sys.argv[1:]])


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
