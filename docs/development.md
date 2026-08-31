# Development guide

## Project structure

The pipeline is intentionally split into reusable stages:

1. `media.py` prepares or inspects local and YouTube inputs.
2. `detect.py` and `auto_timeline.py` discover gameplay candidates and refine boundaries.
3. `recognition.py` and `result_stats.py` extract song, chart and optional player-result evidence.
4. `analysis.json` persists the result independently of presentation.
5. `timeline.py`, `rendering.py` or an executable TypeScript formatter produce user-facing text.
6. `evaluate.py` compares automatic output with an independent video review.

The main package is under `src/piu_timeline/`. Tests mirror the modules under `tests/`. Native macOS Vision OCR lives in `native/ocr.swift`. TypeScript formatting examples live in `templates/`.

## Development setup

The normal setup expects Python 3.12, FFmpeg, Deno and `just`:

```sh
./scripts/bootstrap
just check
```

Bootstrap creates `.venv/`, installs the pinned requirements and verifies the checkout. If the required tools are unavailable, opt into project-local pinned tools:

```sh
PIU_USE_MISE=1 ./scripts/bootstrap
```

Mise data, caches, compiled OCR helpers and temporary artifacts remain under `.local/`. No shell activation is required because `just` recipes run through `scripts/run.sh`.

Dependency sources:

- Python project metadata: `pyproject.toml`
- Reproducible Python installs: `requirements.txt` and `requirements-dev.txt`
- Optional pinned tools: `mise.toml`

## Verification

Run the offline suite after every change:

```sh
just check
```

It includes unit tests and synthetic FFmpeg integration coverage. The real Vision OCR integration is separate because it depends on the macOS host:

```sh
just check-ocr
```

Check an executable formatter independently with:

```sh
deno check templates/timeline.ts
```

## Artifact and data policy

- Put generated artifacts under `.local/outputs/`.
- Keep downloaded originals under the ignored `data/raw/` tree.
- Keep comments and other noisy reference material under `data/labels/`.
- Put reviewed/evaluation fixtures under `data/derived/` only when they are suitable for version control.
- Never commit credentials, downloaded video, private comments or generated reports.
- Never overwrite source media or silently change its timebase.

Output commands normally require a new destination. This protects earlier evidence and makes failed or partial runs distinguishable from completed artifacts.

## Recognition invariants

- Comments are not detector inputs and are not ground truth.
- Unknown, conflicting or insufficient OCR evidence remains `null`.
- Player slots remain separate; one player's values must not fill another player's missing fields.
- OCR confidence is evidence, not a calibrated correctness probability.
- Local playback time and YouTube time remain distinct unless a review supplies an explicit offset.
- Automatic gameplay boundaries do not establish the silent publication boundaries described in the README.

## Common development commands

```sh
just --list
just probe VIDEO
just analyze VIDEO OUTPUT
just auto VIDEO OUTPUT
just relabel OLD_ANALYSIS NEW_OUTPUT
just results OLD_ANALYSIS NEW_OUTPUT
just format ANALYSIS_JSON OUTPUT_TEXT
just evaluate PREDICTION REFERENCE OUTPUT_JSON
```

Use `just analyze` when changing detection or recognition so completed analysis survives presentation failures. Use `just relabel` when retained OCR evidence is sufficient and decoding the full video again would add no information.

## Design and validation records

- [Scene and OCR notes](scene-and-ocr-notes.md) records observed scene flow and recognition behavior.
- [Layout and result design](layout-and-result-design.md) records implemented and proposed layout decisions.
- [Validation](validation.md) records measured behavior and known limits.
- [Timeline presentation](result-templates.md) documents executable formatting and saved player results.

Keep measured validation claims in `validation.md`, not in the README. Keep proposals clearly separated from implemented interfaces.

Codex-specific shell and sandbox behavior is documented separately in [Codex development environment](codex-environment.md).
