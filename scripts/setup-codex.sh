#!/bin/sh
set -eu
PIU_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$PIU_ROOT/scripts/env.sh"
cd "$PIU_ROOT"

if [ "${PIU_USE_MISE:-0}" = 1 ]; then
  if [ ! -x "$PIU_ROOT/.local/mise_home/bin/mise" ]; then
    mkdir -p "$PIU_ROOT/.local/mise_home/bin"
    curl -fsSL --retry 3 https://mise.run -o "$TMPDIR/mise-install.sh"
    MISE_VERSION=v2026.8.14 MISE_INSTALL_PATH="$PIU_ROOT/.local/mise_home/bin/mise" \
      sh "$TMPDIR/mise-install.sh"
  fi
  sh scripts/mise trust "$PIU_ROOT/mise.toml"
  sh scripts/mise install
  sh scripts/mise reshim
fi

PYTHON=${PYTHON:-python3}
command -v "$PYTHON" >/dev/null || { echo "Python 3.12 is required." >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "FFmpeg is required." >&2; exit 1; }
command -v ffprobe >/dev/null || { echo "ffprobe is required." >&2; exit 1; }
command -v node >/dev/null || { echo "Node.js 24 or newer is required." >&2; exit 1; }
command -v just >/dev/null || { echo "just is required." >&2; exit 1; }
"$PYTHON" -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 12))' || {
  echo "Python 3.12 is required." >&2
  exit 1
}
node -e 'const major=Number(process.versions.node.split(".")[0]); process.exit(major >= 24 ? 0 : 1)' || {
  echo "Node.js 24 or newer is required." >&2
  exit 1
}

"$PYTHON" scripts/bootstrap.py
.venv/bin/python scripts/configure_codex.py
just check
