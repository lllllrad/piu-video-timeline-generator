"""Prepare the checkout's Python environment before a recipe runs."""
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def prepare(root=ROOT):
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Python 3.12 is required; run mise exec -- just auto SOURCE.")
    environment = root / ".venv"
    environment.mkdir(parents=True, exist_ok=True)
    # Serialize creation and installation, including concurrent first runs.
    with (environment / ".bootstrap.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        python = environment / "bin/python"
        if not python.exists():
            print("Preparing project Python environment...", file=sys.stderr)
            venv.create(environment, with_pip=False)
        digest = hashlib.sha256(b"uv-pip-v1\0" + str(root.resolve()).encode())
        for name in ("pyproject.toml", "requirements.txt", "requirements-dev.txt"):
            digest.update((root / name).read_bytes())
        signature = digest.hexdigest()
        marker = environment / ".bootstrap.json"
        try:
            state = json.loads(marker.read_text())
        except (OSError, ValueError):
            state = {}
        if state.get("signature") != signature:
            print("Installing project dependencies...", file=sys.stderr)
            command = ["uv", "pip", "install", "--python", str(python), "-r", "requirements-dev.txt"]
            # Keep stdout reserved for the requested command's result.
            subprocess.run(command, cwd=root, check=True, stdout=sys.stderr)
            marker.write_text(json.dumps({"signature": signature}) + "\n")


if __name__ == "__main__":
    prepare()
