set -eu
PIU_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$PIU_ROOT/scripts/env.sh"
cd "$PIU_ROOT"
exec "$@"
