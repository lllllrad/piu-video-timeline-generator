set -eu
PIU_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$PIU_ROOT/scripts/env.sh"
cd "$PIU_ROOT"
if [ "${1:-}" = .venv/bin/python ]; then
  bootstrap_python="$PIU_ROOT/.venv/bin/python"
  if [ ! -x "$bootstrap_python" ]; then
    bootstrap_python="${PYTHON:-python3}"
  fi
  "$bootstrap_python" scripts/bootstrap.py
fi
exec "$@"
