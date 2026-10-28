# Development

## Setup

The project requires Python 3.12, uv, FFmpeg, Node.js 24 or newer, pnpm and `just`.

```sh
mise install
mise exec -- pnpm install --frozen-lockfile
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

See [the current play data flow](play-data-flow.md) for stage ownership, stored
artifacts, independent stage reuse and the limits of current validation.

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
acquisition/cache orchestration and note association. The evidence inspector shell and SVG renderer live in `play/report.html`,
`play/report.css` and `play/report.js`; `play/inspector/` owns tab navigation,
provenance, channel overlays and workspace styling. `play/report.py` renders
prepared data into each standalone HTML result.
These resources are included in built Python wheels.

`play/channels.py` exposes the four retained visual evidence channels and match
provenance; `play/processing/` observes head persistence and disappearance at
receptors independently of HUD values. See [visual channels](visual-channels.md)
for artifacts, count units, uncertainty and association rules.

`play/object_roles.py` interprets explicitly configured decorative artwork before
track and motion reconstruction. Its frame-level roles retain raw detection
identity and source PTS; [object roles](object-roles.md) describes the scope and
uncertainty contract. Pixel acquisition remains independent of these roles.

`play/skins/` owns RGB reference banks, direct image detection, observed cap roles
and image-based hold geometry. Direct reference-anchor measurements are retained
by `play/skins/coordinates.py` with original PTS and cap-comparison provenance;
independent beat-spacing checks consume them without asserting absolute game
calibration. See [note-skin images](note-skin-images.md).

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
- `play/tracking.py` locates colored note-head outlines, bridges bounded UI occlusions, distinguishes repeated render frames from nonlinear motion, learns combo digit templates and aligns judged rows with confirmed combo updates. A chord occupies one judged row. Compatible native observations can be refitted without frame decoding or OCR; font examples are reusable across plays from unchanged source media. It does not equate display refresh with physical switch input.
- `formats/` contains Node.js TypeScript presentation programs. `formats/lib/timeline.ts` separates song labels, player names and recording-aware segment labels; both bundled formats share the same automatic name-visibility policy. See [custom formats](formats.md).
- `tools/timeline.py`, `tools/evaluate.py` and `tools/relabel.py` are internal review and diagnostic tools.

Analysis is authoritative and presentation is disposable. A format reads `analysis.json`; it does not trigger recognition or mutate evidence.
Analyzer changes that affect saved results increment `ANALYSIS_VERSION`. `just auto` rebuilds an
older cache into a unique temporary directory and replaces it only after the new analysis succeeds.
Source size/mtime, explicit game ROI and OCR backend/device changes invalidate the cache too. A
per-source advisory lock prevents concurrent writers on macOS/Linux. Existing results are retained
in `analysis.previous-*`; interrupted builds remain in `analysis.build-*` for diagnosis. Promotion
rewrites nested evidence paths to their final location. Original media is never rewritten.

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

Replay defaults to completed canonical plays with saved native frames. It
checks artifact contracts and source identity before calling the public play
command for outdated results. `--acquire` also includes metadata plays without
saved observations; `--watch` discovers later promotions every 30 seconds.
Independent play commands run concurrently. `--jobs` defaults to half the
available CPU affinity, capped at eight processes; `--jobs 1` requests serial
execution. The coordinator writes progress, including all active plays; each
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
rule scan without tests. QG automatically installs its pre-commit hook on first
use, preserving an existing custom hook. The hook checks staged files and runs
the shared tests from `.qg.yaml` against the working tree.

Quality Gate and its JS/TS rules are project-local pnpm development dependencies, pinned in
`package.json` with its transitive dependencies locked in `pnpm-lock.yaml`.
Run `pnpm install --frozen-lockfile` after cloning or updating the lockfile; its prepare script installs
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

```sh
sh scripts/run.sh .venv/bin/python scripts/regenerate.py --jobs 3
```

This runs `just auto` over cached source IDs, without downloading media when each `raw/` directory contains one completed recording. Per-source logs and a report with exit status, elapsed time and before/after source metadata are saved in `.local/runs/regeneration-*/`. Failed sources do not prevent the remaining sources from running. The command exits non-zero if any source failed or changed. Keep concurrency low on GPU hosts to avoid loading multiple model copies into limited VRAM.

Source-time boundary comparisons use a one-microsecond floating-point tolerance.
Original PTS and playback values are retained without rounding or retiming.
Counter/row derivation has a separate `timing_format` contract: a timing-rule
change refits saved native observations and replays word reads without repeating
OCR or invalidating native appearance pixels.

The first native pass also retains exact counter-region RGB pixels in
`counter-pixels.npz`. Recovery and improved digit templates reuse these pixels;
legacy analyses acquire this small region once when needed. Source, geometry,
frame count and original timestamps are validated independently of digit reads.
Changing an association rule never invalidates this pixel cache.

A counter burst can be split only when every intervening value is independently
read with high confidence in the native pixels. Validate each resulting transition
against the ordinary capture-gap limit; a longer parent interval alone does not
invalidate short, fully observed substeps. A slow or absent substep, contextual
digit guess, reversal or unconfirmed ending keeps the original unresolved event.

Faded combo glyphs may fall below a fixed white threshold. When ordinary reads
fail, the reader measures neutral-pixel contrast with Otsu separation and tests
both that mask and a threshold halfway toward the usual white threshold. Both
must independently identify the same number with the existing template score
and ambiguity limits; the expected counter never selects this fallback. Reader
identity is part of the timing contract, so changes replay saved counter crops
while preserving native note observations. Legacy plays acquire this crop once.

A judgment-association upgrade with compatible saved word observations replays
those reads without refitting note trajectories. Reader/template changes retain
the isolated rebuild path; they must not rewrite the live observation trace
through the association-only fast path. Refreshed association contracts are
persisted even when no long-note or channel artifacts change.

`play/screen_regions.py` names known foreground HUD footprints.
`play/continuity.py` and `play/motion_warnings.py` audit native detection gaps,
premature endings, speed changes and possible stops independently of fit or
input success. See the [gameplay screen map](gameplay-screen-map.md). Their
versioned `visibility-diagnostics.json` is derived from saved frames without
decoding or OCR; replay refreshes an older diagnostic contract through report
generation. Generic timing exclusions do not suppress these checks.

Python adapters prepare acquisition objects for TypeScript `derived/tracks.ts`,
`derived/registration.ts`, `derived/fragments.ts` and `derived/clocks.ts`, which rebuild displacement
and subframe clocks from registered trajectory identities. Gap stitching and
its uniqueness checks run in TypeScript; Python only adapts acquisition tracks.
For a registered HUD gap, all intact approach coordinates constrain one shared
anchor interval. Every initial reappearance must intersect that same interval
under its own existing coordinate budget. A noisy endpoint cannot select the
anchor alone, and separate feasible anchors for separate frames do not prove
continuity. Conflicting references and competing successors remain separate.
Accepted registered connections retain their reference/reappearance coordinates,
original source PTS and common offset range in `fragment_connections`. `derived/beats/`
checks every co-observed neighboring head, including chords and close staggers,
against independent coordinate references; a small relative gap cannot exempt a
shared absolute timing error. It uses prepared official UCS timing and verified
alignment to test natural subdivisions. Missing references, failed shared
support and ambiguous beat rows remain explicit review states. Candidate refresh
selection also rejects a head independently observed moving sufficiently after
the refresh, using the same guarded passage check as confirmed associations.
Unverified, broad or temporally overlapping passage never proves this conflict. Native video,
frame traces and pixel caches are reusable across these derived-rule changes.

## Measuring scroll-speed changes

`just _chart-motion --sources VIDEO_ID --charts S23` estimates concrete speed
changes from saved `registered_peer_displacement` samples. It reads native
motion and verified source/alignment identities without decoding video, OCR or
new audio alignment. The default is read-only; `--write` appends qualified,
provisionally active effects to the separate chart repository. Measurements and
rejected-window reasons stay in `.local/reports/chart-motion/report.json` (or
an explicit `.local/` output path). Missing acquisition, changed media and
unsupported alignment fail explicitly; no proposal does not clear warnings.

The source filter includes all completed, registered recordings of a selected
chart, not only the recording that originally generated its draft. An alternate
recording needs its own reviewed explicit origin or source/window/reference-bound
audio alignment cache; the seed recording's origin is never copied. Missing or
stale alignment fails explicitly without downloading or decoding audio. Each
proposal retains the actual recording's identity and full alignment evidence.

The estimator compares approximately 300 ms linear displacement windows with
at least 12 native samples, 70% independent multi-lane support and sufficient
pixel displacement. Error bounds include fit error and a 1.5-pixel positional
floor. A phase-continuous intersection must agree with the intervening native
frames. Repeated render frames are tolerated without treating every stationary
sample as a stop. Automatic registration requires the current joint native-coordinate contract; older
integrated phases remain review proposals and cannot be written as chart effects.
It additionally requires at least three
peer heads, consistent longer native flanks (at least 400 ms on each side),
a relative ratio interval width of at most 15%, a native transition
bracket no wider than 100 ms and no other proposed change within 600 ms.
Gradual ramps, densely repeated changes, stops, reversals and sparse observations
can remain unresolved; they retain their original warnings.

`scroll_speed_change.speed_multiplier` is the measured **after/before screen
velocity ratio**, not an absolute game speed setting. Evidence retains velocities
in analysis pixels per second, lane spacing, original PTS, fit errors and the
nominal UCS BPM before and after. BPM ratio and measured ratio are separate;
neither a presumed half/double multiplier nor a musical grid replaces the
observations. Song-relative transition bounds include alignment uncertainty.

Pending and confirmed effects apply immediately. The concrete handler checks a
piecewise trajectory against each actual head before using it to inspect retained
processing pixels. Only matching native speed-change records are classified as
configured motion; chart reconstruction failures, missing input evidence, type
conflicts and contradictory motion remain warnings. Metadata recording preserves
human edits and rejected effects and deduplicates original-frame evidence.

## Bounded warning review

Use `just _replay --warning-limit 20 --jobs 8` to collect a small batch before
investigating and changing rules. Only current artifacts or successfully refreshed
plays contribute cases. The limit counts distinct unresolved warning cases collected
in this run, not newly introduced regressions or different warning kinds. Both recognition failures and unaccounted excluded trajectories contribute;
identical cases present in both files count once. Each
play contributes representatives of different reasons before repeated cases.
`warning-batch.json` retains the original records and report links; all remaining
cases stay in the original warning files. Collection neither acknowledges nor
suppresses anything. Repeated cycles deduplicate cases inside the run; a new run
still exposes unfixed cases.

At the limit the coordinator stops scheduling, lets active children finish, records
`warning_limit_reached` and exits, including with `--watch`. A parallel batch can
therefore finish more plays than strictly necessary. Review the queue, fix a general
rule or add a concrete chart-specific handler/annotation, run checks, and then start
the next batch. Missing or malformed warning artifacts fail explicitly. Omit the
limit only when a complete acquisition or contract refresh is intended.


After inspecting a queue, pass `--reviewed-batch PATH/TO/warning-batch.json` to
the next run (repeat the option for multiple inspected batches). Those identities
are excluded only from the new review queue, so the next batch can discover
additional cases. The original warnings, failure checks and totals remain intact;
previous inspection is never a recognition exemption. Keep unresolved inspected
cases in a local review log with their reason and follow-up. A batch file should
be passed only after inspection, not automatically marked reviewed on collection.

Beat reconstruction prepares verified reference-audio translation before fitting
rows, even when an existing chart has no region annotations or suspected effects.
`charts/audio.prepare_alignment` is shared by beat preparation and chart policy;
it reuses a matching seed, explicit origin or source-bound alignment cache.
Reference/current checks themselves remain read-only and never decode audio or
fetch reference files. Failed preparation remains an explicit beat warning with
the alignment error; it does not silently fall back to a guessed song origin.

`derived/registration.ts` refines registered displacement with a matrix-free
solve of the head-overlap Laplacian and robust native-position weights. It
runs on saved detections without numerical-library dependencies. Its diagnostics are
retained under `scroll_motion.coordinate_registration`; failed blocks cannot
provide shared distances, target clocks or automatic speed estimates. Native
source-position conflicts remain separate reconstruction warnings.

Font discovery reads the acquisition header before the top-level `notes` array,
rather than parsing other plays' trajectories and derived channels. Candidate
fonts still have to pass the same current-recording pixel validation; this I/O
optimization does not transfer counter values or weaken validation thresholds.
