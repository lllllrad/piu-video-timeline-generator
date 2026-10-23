# Development

## Setup

The project requires Python 3.12, FFmpeg, Node.js 24 or newer and `just`.

```sh
mise install
mise exec -- just check
mise exec -- just auto SOURCE
```

Recipes automatically create `.venv` and install the project dependencies. `requirements.txt` includes EasyOCR on Linux using a platform marker. Installation is serialized across concurrent recipes and cached under `.venv`; changes to dependency declarations trigger an update. Failed installations are retried on the next run. If the required tools are already on PATH, `just` can be used directly.

No shell activation is required; recipes use `scripts/run.sh` to apply project-local cache paths and invoke `.venv` explicitly.

Codex-only environment generation and optional mise installation are documented in [codex-environment.md](codex-environment.md). They are not part of normal project setup.

## Architecture

- `workflow.py` owns the public `just auto` flow, stable source IDs and `.local/data/` layout.
- `media.py` prepares YouTube media with yt-dlp or inspects local input.
- `auto_timeline.py` detects gameplay, refines boundaries and saves structured evidence.
- `ocr.py` adapts Vision or EasyOCR to the same normalized, top-left image coordinates. EasyOCR readers are reused within a process; models stay under `.local/cache/`.
- `recognition.py` classifies observed screens and parses layout-specific fields.
- `evidence.py` resolves labels, player identity and stage-row associations across a credit.
- `credits.py` samples screen transitions inside gameplay gaps and groups plays using observed credit boundaries.
- `result_stats.py` extracts per-player result fields only from per-song results.
- `formats/` contains Node.js TypeScript presentation programs.
- `timeline.py`, `evaluate.py` and `relabel_analysis.py` are internal review and diagnostic tools.

Analysis is authoritative and presentation is disposable. A format reads `analysis.json`; it does not trigger recognition or mutate evidence.
Analyzer changes that affect saved results increment `ANALYSIS_VERSION`. `just auto` rebuilds an older cache into a unique temporary directory and replaces it only after the new analysis succeeds. Source size/mtime, explicit game ROI and OCR backend/device changes invalidate the cache too. A per-source advisory lock prevents concurrent writers on macOS/Linux. Existing results are retained in `analysis.previous-*`; interrupted builds remain in `analysis.build-*` for diagnosis. Promotion rewrites nested evidence paths to their final location. Original media is never rewritten.

Version 27 uses English OCR to locate the fixed `STAGE` HUD label and reuses source-verified acquisition from versions 5–26. It preserves decoded gameplay boundaries and saved result frames, adds early/transition samples, and reads dedicated account strips. Result statistics are recomputed from the union of retained and newly acquired evidence. Unresolved numeric fields, conflicts between full-screen and numeric-only OCR, and uncorroborated badges receive caption-preserving crops on at most six new source frames per play to prevent rotated digit recognition; missing HUD stages receive enlarged anchored crops. Scores still unreadable after contextual recovery receive a separate contrast channel on at most six source frames. Other versions or changed input/settings receive a complete rebuild. Only the new complete analysis is promoted.

## Commands

The public interface intentionally stays small:

```sh
just auto SOURCE [FORMAT]
just fetch URL_OR_ID
just import-studio URL_OR_ID VIDEO_PATH
just check
just check-ocr
```

Private recipes beginning with `_` support direct review and diagnostics without appearing in `just --list`.

## Verification

```sh
just check
node formats/default/index.ts PATH/TO/analysis.json
```

`just check` is offline after the initial dependency setup and includes unit tests plus synthetic FFmpeg integration. `just check-ocr` separately exercises the host Vision implementation.

## Data and recognition rules

- Keep downloaded media, analysis output, caches and personal formats under `.local/`.
- Never overwrite or retime source media.
- Preserve unknown and conflicting OCR values as `null` or explicit field states.
- Keep P1 and P2 result evidence separate.
- Keep local playback time distinct from YouTube time unless an explicit reviewed offset exists.
- Automatic gameplay boundaries do not establish silent publication boundaries.

Design observations are in [scene-and-ocr-notes.md](scene-and-ocr-notes.md) and [layout-and-result-design.md](layout-and-result-design.md). Keep corpus-specific validation reports and execution logs under ignored `.local/`; commit reusable tests and design guidance only.

## Linux and accelerator setup

Recipes install EasyOCR automatically on Linux from `requirements.txt`. The Linux backend is EasyOCR 1.7.2, using Korean and English readers. The base install on macOS remains lightweight.

- `PIU_OCR_BACKEND=auto` selects Vision on macOS and EasyOCR elsewhere.
- `PIU_OCR_BACKEND=vision|easyocr` explicitly chooses a backend.
- `PIU_OCR_DEVICE=cpu` is the portable default for EasyOCR.
- `PIU_OCR_DEVICE=auto` asks EasyOCR to use available acceleration with CPU fallback.
- `PIU_OCR_DEVICE=cuda`, `cuda:0`, or `mps` selects a device supported by the installed PyTorch build.

Install a PyTorch build compatible with the server's accelerator before running GPU inference. Backend/device changes rebuild saved analyses. The shared geometry is tested offline; Linux CPU/GPU OCR accuracy is not assumed equivalent to Vision and requires representative-video validation on that host. First use may download model weights, so provision `.local/cache/easyocr` before offline server operation. Refer to the [EasyOCR API](https://jaided.ai/easyocr/documentation/) for the upstream device/model contract.

## Full local regeneration

```sh
sh scripts/run.sh .venv/bin/python scripts/regenerate.py --jobs 3
```

This runs the existing `just auto` interface over cached source IDs, without downloading media when each `raw/` directory contains one completed recording. Per-source logs and a report with exit status, elapsed time and before/after source metadata are saved in `.local/regeneration-*/`. Failed sources do not prevent the remaining sources from running. The command exits non-zero if any source failed or changed. Keep concurrency low on GPU hosts to avoid loading multiple model copies into limited VRAM.
