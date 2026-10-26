set positional-arguments

# Analyze a local video or YouTube URL and print a named timeline format.
auto +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.workflow auto "$@"

# Analyze visible notes and combo timing; save a local HTML report.
play +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.play.analysis "$@"

# Manage official UCS timing and editable chart drafts in a separate repository.
charts +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.charts.data "$@"

# Download a YouTube video into the cache used by `auto`.
fetch +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.workflow fetch "$@"

# Move a YouTube Studio export into the cache used by `auto`.
import-studio +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.workflow import-studio "$@"

# Run the full recommended QG rules and the test suite.
check:
    sh scripts/run.sh npm exec --no -- qg check --full

# Run Quality Gate; defaults to staged rules plus the test suite.
qg *args:
    sh scripts/run.sh npm exec --no -- qg "$@"

# Exercise the native macOS Vision OCR engine.
check-ocr:
    sh scripts/run.sh .venv/bin/python tests/integration/vision_ocr.py

# Internal diagnostics and review tools. Leading underscores keep these out of `just --list`.
_probe path:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.media "$1"

_record path:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.tools.timeline record "$1"

_review video output:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.tools.timeline review "$1" "$2"

_timeline +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.tools.timeline generate "$@"

_frames +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.tools.timeline frames "$@"

_detect +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.vision.detect "$@"

_evaluate +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.tools.evaluate "$@"

_relabel +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.tools.relabel "$@"

# Refresh completed play caches, optionally acquiring missing plays or watching promotions.
_replay *args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.tools.replay "$@"

# Classify saved recognition warnings without changing source media or analyses.
_audit *args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.tools.audit "$@"

# Measure concrete scroll-speed changes from retained registered motion.
_chart-motion *args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.tools.chart_motion "$@"

# Review skin tail appearance separately from the current UCS processing gate.
_visual-support *args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.tools.visual_support_review "$@"
