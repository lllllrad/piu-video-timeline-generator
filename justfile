set positional-arguments

# List available recipes.
default:
    @just --list

# Install pinned tools into .local and verify them.
bootstrap:
    ./scripts/bootstrap

# Run offline tool checks and tests.
check:
    ./scripts/mise run check

# Download a seed ID or YouTube URL; accepts --metadata-only or --comments.
fetch +args:
    ./scripts/mise run fetch -- "$@"

# Inspect a local video without a network request.
probe path:
    ./scripts/mise run probe -- "$1"
