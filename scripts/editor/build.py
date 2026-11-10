"""Build the shared DCM package as a verified local tarball, then compile the review UI."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def run(*args, cwd=ROOT):
    subprocess.run(args, cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', type=Path, default=ROOT / '.local/dcm')
    parser.add_argument('--update-lockfile',action='store_true',help='Update the root lock after an intentional DCM pin change')
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    pin = json.loads((ROOT / 'scripts/editor/dcm.json').read_text())
    if not checkout.exists():
        run('git', 'clone', '--no-checkout', pin['repository'], str(checkout))
        run('git', 'checkout', '--detach', pin['revision'], cwd=checkout)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip()
    if revision != pin['revision']:
        raise SystemExit('DCM checkout differs from the pinned base. Use --checkout with a separate clean directory.')
    package = checkout / 'packages/chart-editor'
    dirty=subprocess.check_output(['git','status','--porcelain','--','packages/chart-editor'],cwd=checkout,text=True)
    if dirty:
        raise SystemExit('Commit shared-package changes before building a pinned tarball')
    if (package / 'dist').exists():
        shutil.rmtree(package / 'dist')
    compiler=ROOT/'node_modules/.bin/tsc'
    if compiler.exists():
        run(str(compiler),'-p',str(package/'tsconfig.json'))
    else:
        run('pnpm','--package=typescript@7.0.2','dlx','tsc','-p',str(package/'tsconfig.json'))
    destination = ROOT / '.local/editor'
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f'piu-chart-editor-{revision[:12]}.tgz'
    run('pnpm', 'pack', '--out', str(archive), cwd=package)
    manifest = {'repository': pin['repository'], 'revision': revision,
                'tarball':archive.name,
                'tarball_sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    (destination / 'package-build.json').write_text(json.dumps(manifest, indent=2) + '\n')
    run('pnpm', 'install', '--no-frozen-lockfile' if args.update_lockfile else '--frozen-lockfile')
    run('pnpm', 'exec', 'tsc', '-p', 'web/review/tsconfig.json')
    app = destination / 'app'
    for name in ('index.html', 'style.css'):
        shutil.copyfile(ROOT / 'web/review' / name, app / name)
    shared = ROOT / 'node_modules/@piu/chart-editor/dist'
    shutil.copytree(shared, app / 'shared', dirs_exist_ok=True)
    print(f'Editor ready: {app}')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
