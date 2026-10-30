# Current play-analysis data flow

This describes implemented stage boundaries, cache dependencies and validation
limits. Stored observations are inputs to independently repeatable consumers.

## Entry points and outputs

`just auto` opens/downloads media, recognizes segment/song/chart/player/result
metadata, and runs a TypeScript timeline format. Its metadata document is
`.local/data/<source>/analysis/analysis.json`.

`just play` consumes that document and analyzes a selected gameplay segment.
Its working directory is `.local/data/<source>/play/segment-NNN/`, with a separate
`analysis.json` and `report.html`. Timeline formatting and play analysis are
separate entry points.

```mermaid
flowchart TD
    media[Original media and source timestamps] --> metadata[Segment and result metadata]
    metadata --> timeline[TypeScript timeline formatting]
    media --> observations[Native frame observations and pixel features]
    metadata --> observations
    observations --> objects[Object interpretation and note tracks]
    objects --> coordinates[Registered coordinates and motion clocks]
    coordinates --> native[Physical timing validation]
    native --> beats[Beat-row reconstruction]
    timing[Official UCS timing and audio alignment] --> beats
    observations --> evidence[Popup, receptor and processing evidence]
    beats --> visible[Visible chart projection with bounded hold geometry and types]
    observations --> visible
    beats --> associations[Counter and judgment association]
    evidence --> associations
    visible --> inspection[Prepared inspection consumers: hold/input view, effects, ranges and diagnostics]
    associations --> inspection
    evidence --> inspection
    inspection --> results[Ordered inspection result]
    results --> composition[Explicit read-model composition]
    composition --> prepared[Prepared report-data.json]
    prepared --> renderer[Pure HTML renderer]
    visible --> chart[UCS draft in separate chart repository]
    timing --> chart
    evidence -. Continuous held-state evidence may support hold simplification .-> chart
    policy[Concrete chart metadata] --> objects
    policy --> inspection
    policy --> chart
```

The diagram groups responsibilities. Public derived stages exchange named result
artifacts with updates restricted to owned fields. Explicit composition builds
downstream read models. Associations are rebuilt when target times or hold
interpretations change.

UCS note placement consumes the visible chart projection rather than successful
input associations. Sustained receptor observations have a separate, limited role
when simplifying adjacent holds; they cannot create or move chart notes. See
[visible chart versus played inputs](chart-data.md#visible-chart-versus-played-inputs).

See [coordinate frames and stage inputs](coordinate-model.md) for position units,
anchor conventions, typed views and consumer permissions.

## Data boundaries

| Stage | Code ownership | Principal stored data |
| --- | --- | --- |
| Metadata | `metadata/`, `vision/`, `workflow.py` | Song/chart/player identity, segment bounds, stage-result OCR |
| Pixel and frame acquisition | `play/observations/`, `play/frames.py`, `play/skins/`, `play/holds/features.py`, `play/judgments.py` | `frames.base.jsonl`, `frames.jsonl`, `judgments.jsonl`, `hold-frames.jsonl`, feature masks and manifests |
| Object/track/coordinate interpretation | `play/object_roles.py`, `play/tracking.py`, `play/head_registration.py`; TypeScript `derived/registration.ts`, `derived/tracks.ts`, `derived/clocks.ts` | Original detections, interpreted tracks, native registration, shared displacement and target-clock evidence |
| Physical timing | `derived/stages/native_timing.ts`, `derived/native_gaps.ts` | `native-timing.json`: physical interval validation and owned timing updates |
| Musical timing | `derived/beats/` (TypeScript), `play/beats/timing.py` (reference preparation) | `beat-result.json`: unique/ambiguous/failed rows, independent-reference proofs and recovery |
| Counter/judgment associations | `derived/stages/associations.ts`; Python `play/judgments.py` acquisition adapter | Counter interpretation, matches and coverage; `judgment-associations.json` |
| Evidence interpretation | Python `play/holds/`, `play/processing/`, `play/channels.py`; TypeScript `derived/labels.ts`, `derived/recovery.ts`, `derived/hold_projection.ts`, `derived/hold_presentation.ts` | Independent native states, popup links, sustained holds, lane effects and unresolved associations |
| Inspection and composition | Python `play/presentation.py` orchestration; TypeScript `derived/pipeline/`, `derived/ranges.ts`, `derived/visibility.ts`, `derived/diagnostics.ts` | `inspection-result.json`: ordered owned outputs; `report-data.json`: explicitly composed read model |
| Rendering and UCS transcription | Python `play/report.py`, `charts/data.py`; TypeScript `derived/report.ts`, `derived/charts/` | HTML and per-measure UCS drafts from their separate prepared inputs |

The four visual channels are popup changes, receptor effects, note movement and
note processing. They preserve separate observations and counts; one popup may
serve a chord, and repeated hold judgments are not repeated presses. Stage-result
counts are a consistency reference. A receptor effect is a visual input proxy,
not a measurement of a physical switch. See [visual channels](visual-channels.md).

Original recordings and source timestamps remain unchanged. Feature masks are
not lossless RGB frames: changing acquisition requirements can require reading
the original video again. Derived-rule changes can often reuse existing frame
observations, but that still involves reading and processing those artifacts.

Official UCS downloads supply timing/BPM structure, not chart-note positions.
Draft notes come from interpreted visible chart evidence. Concrete chart metadata
can authorize special processing; it must not manufacture observations or turn
unexplained conflicts into successes. Editable UCS/chart facts live separately
from this code repository.

## Stage execution and cache reuse

`play/analysis.py` schedules source acquisition/refit, registered coordinates,
musical timing, native judgment/hold measurements, presentation and chart
registration. Scheduling does not give report consumers access to a decoder.

Start reading at `play/analysis.py:run`. It selects one of these paths under the
segment lock:

| Path | Entry point and work |
| --- | --- |
| Compatible saved result | `refresh_saved_play` reuses trajectories and refreshes compatible judgment/hold evidence and the inspector. |
| Saved coordinates, outdated beats | `refresh_saved_play` first rebuilds physical/beat timing and associations from `coordinates.json`, without replaying frames. |
| Saved native observations | `refit_saved` rebuilds tracks and clocks from retained frame records in a pending directory. Detector changes may require native pixels. |
| Fresh acquisition | `analyze_play` reads the recording and retains frame/pixel observations in a pending directory. |

The refit and acquisition paths then call `finish_play`: object interpretation,
head registration and coordinate capture, physical/beat timing, reassociation,
judgment/hold evidence, inspector preparation, pure rendering and atomic directory
promotion. The saved refresh path updates its compatible artifacts directly.
Both paths register chart data separately after the inspector is available.

Follow `play/beats/timing.py:apply` into `derived/stages/native_timing.ts` and
`derived/beats/stage.ts` for timing. Follow `play/presentation.py:prepare_report`
into `derived/pipeline/presentation.ts` for inspection calculation and
`derived/pipeline/composition.ts` for the combined read model; the caller then
invokes `play/report.py:write_report`. UCS uses `charts/data.py:draft` and
`play/holds/analysis.py:chart_projection`, followed by `derived/charts/draft.ts`.

* `coordinates.json` preserves registered pre-beat output with source, geometry,
  producer identity and a content fingerprint. Musical timing has its own
  contract; a beat-only change resumes this boundary without frame replay.
* `coordinates.json` separates original observations and coordinate results,
  excluding HUD associations. `native-timing.json` stores physical validation.
  `beat-input.json` supplies these artifacts and reference text; `beat-result.json`
  stores musical decisions. Explicit composition builds a downstream reader view.
* Native geometry, note processing and type observations have separate cached
  outputs under `native-stages/`. Hold geometry does not depend on HUD refreshes.
  `hold-state-input.json` feeds the independent TypeScript sustained-state stage.
  `holds.json` and `visual-channels.json` assemble these outputs for callers.
* `presentation-input.json` binds prepared external metadata, native proofs and
  compact channel records. TypeScript consumers prepare chart/input views,
  ranges, continuity and diagnostics, with separate artifacts and a dependency
  manifest under `derived-stages/`. Changing a counter observation does not rerun
  the visibility consumer; changing a title does not rerun inference.
* Native processing under configured motion is an explicit measurement producer.
  Its output is bound to the interpreted geometry and concrete motion model.
  A prepared consumer cannot request new pixel reads through a callback.
* `inspection-result.json` contains ordered owned consumer outputs. Composition
  checks their order and field ownership before constructing `report-data.json`.
  Preparation and HTML rendering are separate orchestration calls.
* `report-data.json` feeds the pure HTML renderer. `report-summary.json` feeds
  the index. Re-rendering either view performs no analysis or frame reads.
* `ucs-input.json` stores chart observations, exact reference timing and alignment
  for an independent UCS draft. Chart-repository registration is a separate I/O
  operation that preserves human edits.

Artifact reuse requires matching declared inputs and producer identities.
Bound results also carry an `input_fingerprint`; composition rejects a result
from different observations or a different prepared request even when note IDs
and counts agree. Explicit segment-root normalization preserves this binding
through pending-directory promotion. See [bound results](derived-analysis.md#reusable-boundaries).
Corrupted output hashes or contradictory source timelines fail explicitly.
The maintenance scheduler checks the stage manifest and native producers before
classifying an analysis as current. Existing plays produce these artifacts on
an ordinary `just play` refresh; no data-migration command is required.

Native detector/geometry refits still use a pending segment and atomic directory
promotion. That transaction can copy retained acquisition artifacts. It does not
make downstream rule changes require a native refit or original-video decoding.
Changed acquisition requirements can require the original recording; retained
feature masks cannot supply pixels they never captured.

See [derived analysis](derived-analysis.md) for stage contracts and standalone
replay commands.

## Validation and geometry scope

Beat/reference/spacing acceptance limits now use fractions of measured lane
spacing. Stored source coordinates and review measurements can remain pixel
valued, with the model's scale recorded explicitly. Time limits remain seconds.
Missing scale is not replaced by an assumed game resolution. Actual raster and
template measurement uncertainty remains distinct from an acceptance threshold.

Other acquisition and motion-fitting code still contains pixel-valued precision
constants. This change does not claim that every stage is resolution invariant.

The chart-derived observation generator and JSON-to-beat-to-UCS-row matrix are
described in [testing](testing.md). They cover natural rhythms, chords, close
staggers, geometry, lane count and frame rate at the native-observation boundary.
They do not yet provide broad skin/image, short-hold or four-channel-combination
coverage. Passing these tests is not a measured corpus recognition rate.
