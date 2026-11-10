"""Run browser tests and all browser dependencies inside a pinned container."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
artifacts = root / '.local/editor/artifacts'
artifacts.mkdir(parents=True, exist_ok=True)
image = 'mcr.microsoft.com/playwright:v1.64.1-noble@sha256:2f05f8a734509a7b3f26a912639488ee08f58a7b292d14d62271bcff9038768f'
subprocess.run(['docker', 'run', '--rm', '--network', 'host', '--ipc', 'host', '--read-only',
                '--tmpfs', '/tmp:rw,exec,size=1g',
                '--mount', f'type=bind,src={root},dst=/workspace,readonly',
                '--mount', f'type=bind,src={artifacts},dst=/workspace/.local/editor/artifacts',
                '--workdir', '/workspace', image, 'node', 'scripts/editor/browser.mjs',
                *sys.argv[1:]], check=True)
