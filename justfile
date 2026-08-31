set positional-arguments

# Analyze a local video or YouTube URL and print a named timeline format.
auto +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.workflow auto "$@"

# Download a YouTube video into the cache used by `auto`.
fetch +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.workflow fetch "$@"

# Run the offline test suite.
check:
    sh scripts/run.sh .venv/bin/python -m unittest discover -s tests -v

# Exercise the native macOS Vision OCR engine.
check-ocr:
    sh scripts/run.sh .venv/bin/python tests/ocr_integration.py

# Internal diagnostics and review tools. Leading underscores keep these out of `just --list`.
_probe path:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.media "$1"

_record path:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.timeline record "$1"

_review video output:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.timeline review "$1" "$2"

_timeline +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.timeline generate "$@"

_frames +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.timeline frames "$@"

_detect +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.detect "$@"

_evaluate +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.evaluate "$@"

_relabel +args:
    sh scripts/run.sh .venv/bin/python -m piu_timeline.relabel_analysis "$@"
