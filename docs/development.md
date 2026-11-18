# Development

## Setup

The project requires Python 3.12, uv, FFmpeg, Node.js 24 or newer, pnpm and `just`.

```sh
mise install
mise exec -- python3 scripts/editor/build.py
mise exec -- just check
mise exec -- just auto SOURCE
```

Mise provisions uv and creates and activates `.venv`. The explicit `_.python.venv` setting supports
this requirements-based project without a `uv.lock`; `python.uv_venv_auto` is also enabled. Recipes
create `.venv` when necessary and install the project dependencies with `uv pip install --python
.venv/bin/python`. No pip installation inside the virtualenv is required. `requirements.txt`
includes ONNX Runtime, PyYAML and polygon-processing dependencies on Linux using platform markers.
Installation is serialized across concurrent recipes and cached under `.venv`; changes to dependency
declarations trigger an update. Failed installations are retried on the next run. If the required
tools are already on PATH, `just` can be used directly.

No shell activation is required; recipes use `scripts/run.sh` to apply project-local cache paths and invoke `.venv` explicitly.
Use mise shell activation or `mise exec -- COMMAND` to supply the configured tools.
An editor or agent launched through `mise exec` passes that environment to its
child commands, so `pnpm`, `just` and Git hooks can run directly in that session.
Codex-only environment generation and optional mise installation are documented in [codex-environment.md](codex-environment.md). They are not part of normal project setup.

## Architecture

See [the current play data flow](play-data-flow.md) and [execution contracts](analysis-stage-contracts.md) for stage ownership, stored
artifacts, input loading, [IPC boundaries](ipc-boundaries.md), [independent capture](independent-observations.md) and validation limits.

Use the [coordinate model](coordinate-model.md) when selecting raw image positions,
registered centers or motion offsets.

Read the [gameplay visual model](gameplay-visual-model.md) before changing note geometry or recognition rules. Keep observed game behavior, measurement assumptions and implementation thresholds distinct; passing a test does not establish the visual model.

The optional [native cap-clearance model](note-skin-clearance.md) combines matched
skin images with source-bound background-gap evidence before hold interpretation.
The [hold input-risk model](hold-input-risk.md) separates approach visibility from
the intervals in which a hold can contribute recognition ticks.

The package is organized by responsibility. `workflow.py`, `media.py` and
`storage.py` at the package root provide the public workflow and shared I/O.

| Package | Responsibility | Main entry points |
| --- | --- | --- |
| `metadata/` | Scene planning, song/chart/player recognition, credit association and result fields | `analysis.py`, `recognition.py`, `results.py` |
| `vision/` | OCR backends, screen crops and gameplay-region detection | `ocr.py`, `paddle.py`, `screen.py`, `detect.py` |
| `play/` | Native frame observations, note tracking, input evidence and HTML reports | `analysis.py`, `tracking.py`, `judgments.py`, `report.py` |
| `play/holds/` | Long-note pixel acquisition, geometry, sustained state and projection | `features.py`, `geometry.py`, `state.py`, `analysis.py` |
| `charts/` | UCS timing, official downloads, audio alignment, registration and human-authored policies | `data.py`, `ucs.py`, `official.py`, `policy.py` |
| `tools/` | Review-assisted timelines, evaluation and retained-evidence relabeling | `timeline.py`, `evaluate.py`, `relabel.py` |

Tests mirror these packages under `tests/`. Workflow/presentation tests live in
`tests/workflow/`; synthetic native-video integration and the optional Vision
integration run live in `tests/integration/`. See [testing](testing.md)
for test commands, coverage and validation limits.

The `justfile` defines public commands. Internal Python invocations use package
paths, for example `python -m piu_timeline.play.analysis` and
`python -m piu_timeline.charts.data`. Modules import `piu_timeline.ROOT` for the
checkout root; cache and model paths are independent of module depth.

`metadata/profiles.py` owns HUD profile discovery and boundary refinement.
`play/layout.py` owns fixed and observed receptor geometry; `play/fonts.py`
owns counter-font acquisition and validation. `play/words.py` reads judgment
word pixels and animation refreshes, while `play/judgments.py` owns their
acquisition/cache orchestration and note association. The interval editor in
`web/review/` consumes bounded evidence from `review/server.py`. `play/report.py` renders
prepared data into each standalone HTML result. `play/presentation.py` persists
the inspection result and composed view; callers then invoke the renderer
explicitly. `derived/stages/` declares observation, coordinate, physical timing and
association contracts. `derived/pipeline/composition.ts` assembles inspection
views. See [derived analysis](derived-analysis.md) for wire schemas.
These resources are included in built Python wheels.

`play/object_roles.py` interprets explicitly configured decorative artwork before
track and motion reconstruction. Its frame-level roles retain raw detection
identity and source PTS; [object roles](object-roles.md) describes the scope and
uncertainty contract. Pixel acquisition remains independent of these roles.

`play/skins/` owns RGB reference banks, direct image detection, observed cap roles
and image-based hold geometry. Native comparison adapters in `play/skins/coordinates.py` retain original PTS
and cap-comparison provenance. `derived/skins/localization.ts` selects raster
positions and applies reference-center transforms in TypeScript;
independent beat-spacing checks consume them without asserting absolute game
calibration. See [note-skin images](note-skin-images.md).

`play/skins/repository.py` publishes immutable image-bank revisions into the
separate data repository and validates their exact content binding. Shared
`skins/sources/` profiles select revisions before acquisition; explicit play
paths override them. `just skins validate` checks the installed native assets
and selections. Image validation uses the native loader; synthetic storage and
selection regressions run through the TypeScript test suite.

- `workflow.py` owns the public `just auto` flow, stable source IDs and `.local/data/` layout.
- `media.py` prepares YouTube media with yt-dlp or inspects local input.
- `metadata/analysis.py` detects gameplay, refines boundaries and saves structured evidence.
- `vision/ocr.py` adapts Vision or PaddleOCR to normalized, top-left coordinates. Official PaddleOCR PP-OCRv5 detection and Korean/English recognition run through `vision/paddle.py` on Linux. Sessions and a bounded cache of exact image-content results are reused within a process; models stay under `.local/cache/`. Cache entries distinguish language, backend, device and pinned model/preprocessing identity, return independent result objects, and retain each observation's original source timestamp.
- `vision/screen.py` reads English UI regions for scene routing. Linux OCR crops a decoded image with Pillow; Vision uses FFmpeg without adding a Python imaging dependency.
- `metadata/recognition.py` classifies observed screens and parses layout-specific fields.
- `metadata/evidence.py` resolves labels, player identity and stage-row associations across a credit.
- `metadata/credits.py` samples screen transitions inside gameplay gaps and groups plays using observed credit boundaries.
- `metadata/results.py` extracts per-player result fields only from per-song results.
- `play/holds/analysis.py` orchestrates hold analysis and projects a hold-aware chart without
converting ticks into presses. `play/holds/features.py` acquires and caches native-frame pixels;
`play/holds/geometry.py` resolves head/body/tail geometry in explicit pixel coordinates;
image start/body/end connectivity is measured independently of endpoint clocks.
`hold_analysis.image_connections` retains unique connected image objects even
when endpoint timing fails. Timed `holds` reference them by `image_connection_id`;
`observed_holds` exposes untimed shapes; failed clocks emit `hold_endpoint_timing_unresolved`
and never become invented timing bounds or UCS placements. Body gaps, competing
endpoints and independently observed interior caps remain geometry failures.
Touching template margins cannot join adjacent source holds across another
start/end cap. A rejected spanning proposal does not warn when both endpoints
are accounted for by separate proven objects; their actual timing failures
remain explicit. Adjacent source objects stay separate before UCS held-state
simplification. Physical image
connections cache only native positions, raw detection anchors and image/motion
observations. `derived/holds/image_timing.ts` is a separate cached consumer of
those connections and endpoint timing; changing a clock does not rerun image
measurement. Its warnings cover the complete endpoint observation span, even
when only part of that span supplies positive body coverage.
`play/holds/state.py` attaches independent sustained recognition and receptor-light transitions.
Geometry does not depend on a successful input match. TypeScript `derived/candidates.ts` constrains review
alternatives using refresh ownership, processed-row order and per-lane receptor evidence.
- `play/analysis.py` orchestrates opt-in visual analysis and caches evidence. `play/presentation.py`
  prepares external/native inputs, then TypeScript `derived/pipeline/` executes independently
  cached consumers; `play/report.py` renders the prepared document and
  summaries. The standalone SVG view uses browser-driven CSS transform playback. Bounded time pages
  limit DOM size; video time anchors animations without per-frame note rebuilding. TypeScript
  `derived/ranges.ts` derives review-only alternative refresh intervals and conditional
  neighboring-row bounds from saved evidence without changing confirmed associations or reacquiring
  frames.
- `play/judgments.py` learns a bounded set of judgment-word templates, detects native-frame label/animation refreshes independently of combo visibility, and merges evidence without duplicate note assignments. MISS never becomes a physical input timestamp.
- `play/recovery.py` recovers uniquely constrained tap rows using independent lane onsets, preserving display brackets and source PTS while rejecting shared onsets and competing refreshes.
- `play/frames.py` streams native decoded frames with original PTS and no FPS conversion.
- `play/motion.py` retains online tracking state; TypeScript `derived/clocks.ts` fits shared subframe clocks, and `derived/tracks.ts` registers saved peer-note displacement. It preserves the original frame timeline and capture uncertainty, with local fitting as a fallback when independent motion support is unavailable.
- `charts/official.py` downloads and validates the official song catalogue and blank timing archives. `charts/ucs.py` adapts Python document values to exact TypeScript section timing; `charts/audio.py` aligns reference music without retiming; `charts/data.py` registers editable, unreviewed chart drafts in a separate repository without replacing existing files. See [chart data](chart-data.md).
- `charts/policy.py` validates human-authored song regions, maps them through a recording-specific alignment, applies report processing methods, and scopes automatic-check exceptions without changing native evidence or result quotas. Invalid policies remain visible rather than silently taking effect.
- `play/tracking.py` tracks image-bank note observations, retains original anchors and bridges
  qualified UI occlusions without fitting target clocks. It also contains the native combo
  reader/tracker; `play/associations.py` connects completed timing to counter events. A chord
  occupies one judged row. Compatible native observations can be refitted without frame decoding or
  OCR; font examples are reusable across plays from unchanged source media. It does not equate
  display refresh with physical switch input.
- `formats/` contains Node.js TypeScript presentation programs. `formats/lib/timeline.ts` separates song labels, player names and recording-aware segment labels; both bundled formats share the same automatic name-visibility policy. See [custom formats](formats.md).

Analysis is authoritative and presentation is disposable. A format reads `analysis.json`; it does not trigger recognition or mutate evidence.
Analyzer changes that affect saved results increment `ANALYSIS_VERSION`. `just auto` rebuilds an
older cache into a unique temporary directory and replaces it only after the new analysis succeeds.
Source size/mtime, explicit game ROI and OCR backend/device changes invalidate the cache too. A
per-source advisory lock prevents concurrent writers on macOS/Linux. Successful publication removes
superseded versions and abandoned builds; see [storage retention](local-storage.md).
Promotion rewrites nested evidence paths to their final location. Original media is never rewritten.

The metadata planner schedules OCR from screen transitions before acquiring text. Two small
grayscale frames per second locate changes only in the bounded gaps around gameplay; OCR reads
transition representatives plus sparse guard samples. When no changes are found, song/chart labels
remain unresolved, or no result screen is observed, fixed-offset sampling provides coverage.
Retained OCR and source timestamps are preserved. Dedicated result-number OCR reads at most six
source frames distributed across the observed result duration, preferring frames with directly
observed numeric rows over entrance animations, independent of the number of decoded frames.
Existing contextual and contrast recovery channels remain bounded to six source frames each.

Screen routing reads fixed UI regions in English rather than unconditionally recognizing the full
game image in Korean and English. A carousel of available levels is classified as `browse`, which
can supply identity/boundary evidence but never a selected chart. Aligned judgment captions and
numeric rows can establish a result without the animated SCORE heading. Frames without the fixed
account header or judgment UI read only a small control-text crop, retaining start/mode/failure
detection without scanning names/chart bands over song art. Unknown screens receive at most two new
full-image OCR attempts per pre/post-game window. Song/chart recovery reads at most six new source
frames per eligible scene and window, stopping per-song title/chart reads when distinct frames
agree; frames after an observed return to browsing/selection cannot supply result metadata.
Unreadable values remain unknown. Directly recognized result/browse screens seed small visual UI
templates. Matching fixed judgment-caption color masks or the carousel band can route subsequent or
earlier representatives without OCR. This reuses only the screen kind, never title/account/numeric
text. Later representatives are examined first so settled UI can route entrance animations. Selected
title/identity/statistics frames still read their own UI/account/rival evidence. Templates are local
to one play, and unknown layouts remain unknown. Unfamiliar layouts can still exceed these routing
assumptions and need representative-video validation.

Progress reports include segment elapsed time, inferred/cached OCR image counts and time inside OCR. These counts include individual UI/title/name/numeric crops, not just full source frames. Exact-content cache hits reuse inference only: their observations keep distinct actual source timestamps and are never presented as additional decoded frames.

Source-verified acquisition is reusable independently of the analyzer release or OCR engine: original media identity and game ROI must match and the saved profile/candidate artifacts must exist. An OCR identity change invalidates text, screen decisions and parsed statistics while preserving captured images, original PTS, decoded boundaries and transition plans. Existing image crops are reused. Only the new complete analysis is promoted.

Frame decoding, visual change detection and OCR have separate responsibilities. Gameplay interval
detection uses visual HUD matching. Note-position tracking consumes decoded gameplay frames and
their original timestamps directly, without metadata OCR on each frame. OCR belongs to selected
metadata observations around gameplay, with separate language and region-specific recovery. The
opt-in `just play` path consumes native frames independently of metadata sampling; see [play
analysis](play-analysis.md).

## Commands

The public interface intentionally stays small:

```sh
just auto SOURCE [FORMAT]
just play SOURCE --segment N
just play SOURCE --all
just charts init
just charts add SOURCE --segment N --ucs-index CS349
just charts sync
just fetch URL_OR_ID
just import-studio URL_OR_ID VIDEO_PATH
just check
just qg check --staged
just qg check --full --rules-only
just check-ocr
```

Private recipes beginning with `_` support direct review and diagnostics without appearing in `just --list`.

### Play maintenance

The tracked replay and audit tools support the repeated local maintenance work:

```sh
just _replay --sources VIDEO_ID --segments 12 14 --jobs 8
just _replay --acquire --watch
just _audit --sources VIDEO_ID --segments 12 14
```

Replay defaults to completed canonical plays with saved native frames or a
retired frame workspace. It
checks artifact contracts and source identity before calling the public play
command for outdated results. `--acquire` also includes metadata plays without
saved observations; `--watch` discovers later promotions every 30 seconds.
Independent play commands run concurrently. `--jobs` defaults to half the
available CPU affinity, capped at eight processes; `--jobs 1` requests serial
execution. Each child defaults to at most `available CPUs / --jobs` image
workers, capped at eight, with numerical-library threads defaulting to one.
Explicit `PIU_SKIN_JOBS` and numerical-library environment settings override
those defaults. This shares a CPU budget instead of multiplying two independent
half-machine worker pools. The coordinator writes progress, including all active plays; each
child keeps its own log and segment lock. Busy segment locks are deferred. Failures do not block other plays, and an
unchanged failed input is not retried until its analysis, metadata, selected skin profile or
reference-bank content changes. Source `note-skins.json` profiles are authoritative for automatic
replay, including profile removal; persist a skin selection there to reuse it across maintenance
runs. A one-off `--note-skin` argument does not update those profiles.
`--sources` preserves explicit source priority. Progress, logs and a JSON/HTML
summary go under `.local/runs/`; `--run-dir` selects a destination there.

Audit classifies every saved warning in the selected reports and flags changed
source identity. It reads saved evidence without decoding, OCR or analysis
writes. Incomplete or concurrently replaced reports are listed as errors;
other reports remain available. Output defaults to
`.local/reports/recognition-review/`, configurable with `--output` under `.local/`.
These summaries do not certify chart accuracy or reconcile stage-grade totals.

## Verification

```sh
just check
node formats/default/index.ts PATH/TO/analysis.json
```

`just check` runs the full repository scan with Quality Gate's recommended Git
and file rules, followed by unit tests and synthetic FFmpeg integration. The
root `.qg.yaml` retains the default rule thresholds and registers `.venv/` as
generated output. Files above 500 lines retain the default warning; errors
block the check. `just check-ocr` separately exercises the host Vision implementation.

`just qg` forwards arguments to the upstream CLI. Its default checks staged
contents and runs the same tests; use `check --full --rules-only` for a full
rule scan without tests. Dependency setup installs the project-environment QG hook, preserving existing custom hooks.
The hook checks staged files and runs
the shared tests from `.qg.yaml` against the working tree.

Quality Gate and its JS/TS rules are project-local pnpm development dependencies, pinned in
`package.json` with its transitive dependencies locked in `pnpm-lock.yaml`.
Run `python3 scripts/editor/build.py` after cloning to build the pinned local editor tarball, then use
`pnpm install --frozen-lockfile` for dependency-only updates; its prepare script installs
the QG hook. `just check` and `just qg` use the installed package without fetching
or building the tool. `node_modules/` is ignored, and pnpm keeps its package store under `.local/cache/pnpm/` through `pnpm-workspace.yaml`.
The `js` preset checks source directives, fixture practices and pnpm lockfile
consistency. Native `node-test` checks run the TypeScript suite through QG's test reporter; type errors and failed tests block both the CLI and hook.

## Data and recognition rules

Keep the `.local/` root organized by purpose. `data/`, `formats/`, `cache/`, `bin/`, `mise_home/`
and `tmp/` are runtime locations. Put batch logs and execution manifests under `runs/`, standalone
review reports under `reports/`, local helper scripts under `tools/`, and superseded experiments
under `archive/`. Disposable test files belong in `tmp/`. Do not move a live job's directories until
all producers and consumers have finished; open log files can be renamed without interrupting their
writers. Update relative media links when relocating HTML reports.

- Keep downloaded media, analysis output, caches and personal formats under `.local/`.
- Never overwrite or retime source media.
- Preserve unknown and conflicting OCR values as `null` or explicit field states.
- Unproven identities stay separate with explicit warnings. Require independently
  supported connections and refusal tests; see [identity validation](recognition-validation.md#identity-refusal-checks).
- Keep P1 and P2 result evidence separate.
- Keep local playback time distinct from YouTube time unless an explicit reviewed offset exists.
- Automatic gameplay boundaries do not establish silent publication boundaries.

Design observations are in [scene-and-ocr-notes.md](scene-and-ocr-notes.md) and [layout-and-result-design.md](layout-and-result-design.md). Keep corpus-specific validation reports and execution logs under ignored `.local/`; commit reusable tests and design guidance only.

## Linux and accelerator setup

Recipes install the Linux inference dependencies automatically from `requirements.txt`. The default
backend runs the official `PP-OCRv5_mobile_det`, `korean_PP-OCRv5_mobile_rec` and
`en_PP-OCRv5_mobile_rec` ONNX exports. Model downloads use pinned Hugging Face revisions and
verified SHA-256 checksums under `.local/cache/paddleocr/`. No PaddlePaddle framework, GUI OpenCV or
PyTorch is required for the default OCR path. macOS metadata OCR uses native Vision; visual play
analysis also uses NumPy and OpenCV.

The Korean model includes all modern Hangul syllables. BGR normalization, line-height resizing,
padding, polygon expansion and CTC decoding follow the model export definitions. Text lines are
batched by width; input images and their timestamps are unchanged. No song-name dictionary or
spelling correction is applied. Chart agreement requires at least two source frames with OCR
confidence of .7 or higher; repeated weak digits remain unresolved. References: [Korean
recognizer](https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec_onnx), [English
recognizer](https://huggingface.co/PaddlePaddle/en_PP-OCRv5_mobile_rec_onnx), [text
detector](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det_onnx).

- `PIU_OCR_BACKEND=auto` selects Vision on macOS and PaddleOCR elsewhere.
- `PIU_OCR_BACKEND=vision|paddleocr|easyocr` explicitly chooses a backend. EasyOCR is an optional legacy backend (`pip install easyocr==1.7.2`), not a default dependency.
- `PIU_OCR_DEVICE=auto` selects the ONNX Runtime CUDA provider when installed and available, otherwise CPU.
- `PIU_OCR_DEVICE=cpu` explicitly forces CPU inference.
- `PIU_OCR_DEVICE=cuda` or `cuda:0` requires a compatible GPU-enabled ONNX Runtime. An unavailable explicitly requested device is an error. `mps` is supported only by the optional EasyOCR backend; native macOS Vision needs no device selection.

Install a compatible GPU-enabled ONNX Runtime for CUDA inference; the default package is CPU-only.
OCR identity changes refresh saved text recognition while retaining verified acquisition. Linux and
macOS use different models, so host accuracy is validated with representative recordings rather than
assumed equivalent. Provision `.local/cache/paddleocr/` before offline operation. The [official
model exports](https://huggingface.co/PaddlePaddle) define preprocessing and character dictionaries;
[PaddleOCR DB
postprocessing](https://github.com/PaddlePaddle/PaddleOCR/blob/main/ppocr/postprocess/db_postprocess.py)
describes polygon extraction and expansion.

## Full local regeneration

See [regeneration and replay maintenance](development-replay.md#full-local-regeneration).


## Measuring scroll-speed changes

See [measuring scroll-speed changes](development-replay.md#measuring-scroll-speed-changes).

## Bounded warning review

See [bounded warning review](development-replay.md#bounded-warning-review).

## Effect reference experiments

Use the [reusable RGB effect extraction tool](effect-reference-extraction.md) to
capture original-PTS crops and build candidate animations in TypeScript. Saved
captures support repeated modeling without decoding again; outputs remain under
`.local/` and are not automatically installed in the play analyzer.
