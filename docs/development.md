# Development

## Setup

The project requires Python 3.12, FFmpeg, Node.js 24 or newer and `just`.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
just check
```

No shell activation is required; recipes use `scripts/run.sh` to apply project-local cache paths and invoke `.venv` explicitly.

Codex-only environment generation and optional mise installation are documented in [codex-environment.md](codex-environment.md). They are not part of normal project setup.

## Architecture

- `workflow.py` owns the public `just auto` flow, stable source IDs and `.local/data/` layout.
- `media.py` prepares YouTube media with yt-dlp or inspects local input.
- `auto_timeline.py` detects gameplay, refines boundaries and saves structured evidence.
- `recognition.py` and `result_stats.py` recognize labels and per-player result fields.
- `formats/` contains Node.js TypeScript presentation programs.
- `timeline.py`, `evaluate.py` and `relabel_analysis.py` are internal review and diagnostic tools.

Analysis is authoritative and presentation is disposable. A format reads `analysis.json`; it does not trigger recognition or mutate evidence.

## Commands

The public interface intentionally stays small:

```sh
just auto SOURCE [FORMAT]
just fetch URL_OR_ID
just check
just check-ocr
```

Private recipes beginning with `_` support direct review and diagnostics without appearing in `just --list`.

## Verification

```sh
just check
node formats/default/index.ts PATH/TO/analysis.json
```

`just check` is offline and includes unit tests plus synthetic FFmpeg integration. `just check-ocr` separately exercises the host Vision implementation.

## Data and recognition rules

- Keep downloaded media, analysis output, caches and personal formats under `.local/`.
- Never overwrite or retime source media.
- Preserve unknown and conflicting OCR values as `null` or explicit field states.
- Keep P1 and P2 result evidence separate.
- Keep local playback time distinct from YouTube time unless an explicit reviewed offset exists.
- Automatic gameplay boundaries do not establish silent publication boundaries.

Design observations are in [scene-and-ocr-notes.md](scene-and-ocr-notes.md) and [layout-and-result-design.md](layout-and-result-design.md). Validation measurements belong in [validation.md](validation.md), not the README.
