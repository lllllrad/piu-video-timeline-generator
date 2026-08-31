set positional-arguments

# List available recipes.
default:
    @just --list

# Install pinned tools into .local and verify them.
bootstrap:
    ./scripts/bootstrap

# Run offline tool checks and tests.
check:
    sh scripts/run.sh .venv/bin/python -m unittest discover -s tests -v

# Download a seed ID or YouTube URL; accepts --metadata-only or --comments.
fetch +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.media fetch "$@"

# Inspect a local video without a network request.
probe path:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.media probe "$1"

# Print a normalized media record (offline).
record path:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.timeline record "$1"

# Create an empty direct-video-review manifest (output must not exist).
review video output:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.timeline review "$1" "$2"

# Generate JSON and text from reviewed segments; accepts --youtube.
timeline +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.timeline generate "$@"

# Extract review frames; accepts repeated --at SECONDS.
frames +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.timeline frames "$@"

# Experimental fixed-layout HUD matching; outputs unreviewed candidates only.
detect +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.detect "$@"

# Analyze one video into a new structured JSON/evidence directory; optional --judgments.
analyze +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.analyze "$@"

# Convenience: analyze and immediately render a timeline.
auto +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.auto_timeline "$@"

# Compare automatic output with independent direct-video review.
evaluate +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.evaluate "$@"

# Exercise the real local Vision OCR engine (may require host permission).
check-ocr:
    sh scripts/run.sh .venv/bin/python tests/ocr_integration.py

# Enrich saved analysis frames with judgments; rendering is opt-in.
results +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.enrich_results "$@"

# Render analysis into a new publishable text/JSON directory (offline).
render +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.rendering "$@"

# Run an executable TypeScript formatter over saved analysis JSON.
format input output script="templates/timeline.ts":
    sh scripts/run.sh deno run --quiet --allow-read --allow-write="$2" "$3" "$1" "$2"

# Re-evaluate missing labels from retained OCR evidence without decoding media.
relabel +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.relabel_analysis "$@"
