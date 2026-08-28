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

# Print a normalized media record (offline).
record path:
    ./scripts/mise exec -- python scripts/timeline.py record "$1"

# Create an empty direct-video-review manifest (output must not exist).
review video output:
    ./scripts/mise exec -- python scripts/timeline.py review "$1" "$2"

# Generate JSON and text from reviewed segments; accepts --youtube.
timeline +args:
    ./scripts/mise exec -- python scripts/timeline.py generate "$@"

# Extract review frames; accepts repeated --at SECONDS.
frames +args:
    ./scripts/mise exec -- python scripts/timeline.py frames "$@"

# Experimental fixed-layout HUD matching; outputs unreviewed candidates only.
detect +args:
    ./scripts/mise exec -- python scripts/detect.py "$@"

# Analyze video into structured JSON/evidence only; optional --judgments.
analyze +args:
    ./scripts/mise exec -- python scripts/analyze.py "$@"

# Convenience: analyze and immediately render a timeline.
auto +args:
    ./scripts/mise exec -- python scripts/auto_timeline.py "$@"

# Compare automatic output with independent direct-video review.
evaluate +args:
    ./scripts/mise exec -- python scripts/evaluate.py "$@"

# Exercise the real local Vision OCR engine (may require host permission).
check-ocr:
    ./scripts/mise exec -- python tests/ocr_integration.py

# Enrich saved analysis frames with judgments; rendering is opt-in.
results +args:
    ./scripts/mise exec -- python scripts/enrich_results.py "$@"

# Render analysis or legacy timeline JSON with player selection/templates (offline).
render +args:
    ./scripts/mise exec -- python scripts/rendering.py "$@"
