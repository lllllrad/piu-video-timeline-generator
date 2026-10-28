# Derived analysis runtime

Saved observations are ordinary data, independent of the acquisition language.
Python owns video decoding, image measurements and geometry, source-bound image
proofs, OCR, audio alignment, downloads and acquisition orchestration. TypeScript under `src/piu_timeline/derived/` owns
joint coordinate registration, saved-track and clock fitting, native spacing and
chord checks, common song-phase and beat-row reconstruction, speed estimates,
exact UCS timing and per-measure row transcription, and HTML rendering.
It also owns popup/row association and recovery, hold chart projection, concrete
visibility/counter effects, sustained receptor state, input ranges, continuity
and unresolved-evidence diagnostics. Original visual observations are inputs to these operations.

Python adapters connect acquisition objects and callers to this implementation.
There is one implementation of each migrated fit and consumer. One Node worker
is reused per Python process. Registration and clock
fitting use batches; the beat stage runs the whole phase search and validation
inside TypeScript. Transport errors fail explicitly. There is no Python fallback.
The callback transport exists for callers supplying a phase-scoring function;
the production beat stage supplies its spatial validator directly in TypeScript.

## Reusable boundaries

`coordinates.json` is the registered pre-beat producer output. Its fingerprint
binds data to source identity, geometry, detector and upstream timing contracts.
It preserves original measured positions and source PTS, alongside derived clocks.
Its output can be reused when musical reconstruction changes. A corrupted snapshot
fails explicitly. A legacy result without this snapshot needs an upstream refit.

`beat-input.json` has schema 1 and contains `data`, `reference`, `timing_text` and
optional `preparation`. The reference includes the verified song origin and its
uncertainty, or an explicit unavailable state and reason. TypeScript does not
fetch timing files or prepare audio alignment. Its output is a patch containing
`beat_timing` and, when reconstruction ran, `notes` and `timing_reconstruction`.
It does not echo source media identity. In particular, nanosecond file timestamps
must not make a floating-point round trip through numerical calculations.

Replay a prepared input without Python, OCR or video decoding:

```sh
just derive beats .local/data/SOURCE/play/segment-001/beat-input.json .local/tmp/beats.json
```

The same command supports `coordinates`, `clocks`, `speed` and `ucs`:

* `coordinates`: `tracks`, `timeline`, `height`, `spacing`, `receptor`, `bottom`.
* `clocks`: `state` (samples, geometry and registration evidence), `tracks`,
  `receptor`, `layout`.
* `speed`: a saved analysis document with registered `scroll_motion`.
* `ucs`: `timing_text` and an `endpoints` object mapping IDs to bounded song-time
  intervals. Output contains UCS text, accepted rows, failures and measure proofs.
  Alternatively provide `chart_observations`, `alignment` and optional
  `extend_constant_tempo` to generate the complete draft, including holds and
  collision checks.

The destination must be a separate JSON file. Results are promoted atomically;
failed inference leaves an existing destination unchanged. Inputs, outputs and
recording-specific diagnostics belong under ignored `.local/`.

UCS decimals, delays and beat positions use normalized BigInt rational arithmetic.
Only comparisons against measured seconds convert to floating point. Unsupported
or ambiguous rows retain explicit failures; subdivision does not expand the
time tolerance or replace missing observations.

`presentation-input.json` contains the analysis document, prepared policy and visual
support metadata, source-timestamped position/counter records, named HUD occluders
and verified image-risk proofs. Native proof preparation has its own
`native-stages/risk-proofs.json` cache bound to the geometry, risk evidence and
verified reference-bank extent. Concrete-motion processing measurements include
their exact interpretation input; contradictory measurements fail explicitly.
Preparing these inputs belongs to `play/observations/presentation.py`. It resolves
external metadata and native proof dependencies before calling a consumer.

TypeScript `derived/pipeline/presentation.ts` executes seven small consumers:

| Stage | Inputs | Output |
| --- | --- | --- |
| `hold-view` | Tracks, native holds, channels and prepared risk proofs | Hold-aware chart objects and judgment associations |
| `motion-effects` | Concrete chart effects | Pause and relative-speed models |
| `effect-view` | Interpreted rows, lane/processing evidence and chart effects | Effect-specific associations and visibility interpretation |
| `policy-view` | Interpreted chart and scoped policies | Eligible input associations |
| `timing-ranges` | Targets, input observations and compact counter frames | Target/input ranges and explicit unknowns |
| `visibility` | Native positions, models, HUD geometry and processing states | Explained occlusions, detection gaps and motion warnings |
| `diagnostics` | Original/projected notes, ranges and continuity results | Excluded-track and unresolved-evidence warnings |

Each consumer caches its owned output under `derived-stages/`, keyed by consumed
inputs and implementation dependencies. The manifest records input/output hashes
and which results were reused. Unrelated metadata, such as a title, does not
invalidate inference. Shared contract or pipeline-composition changes can affect
several consumers. Corrupt outputs fail explicitly. Segment-local references use
`@segment/` inside hashed artifacts so directory promotion preserves their identity.
Maintenance checks include producer identities and retained source-file signatures.

Replay the prepared calculation without Python, image libraries, audio, network or
source video:

```sh
just derive presentation .local/data/SOURCE/play/segment-001/presentation-input.json .local/tmp/report-data.json
just render .local/tmp/report-data.json .local/tmp/report.html
```

The standalone `hold-view`, `effects`, `ranges` and `visibility` stages are also
available. `hold-view` uses a presentation request; `effects` and `ranges` consume
an analysis view; `visibility` takes `data`, compact `frames` and `occluders`.

`play/presentation.py` persists diagnostic views and `report-data.json` after the
TypeScript calculation. `play/report.py` renders that prepared document only.
Rendering preserves opaque acquisition metadata and escapes HTML/script delimiters.
`report-summary.json` supplies the index without reading trajectories or running
inference. HTML rendering is independently repeatable:

```sh
just render .local/data/SOURCE/play/segment-001/report-data.json .local/tmp/report.html
```

## Native and sustained-state boundaries

`play/observations/acquisition.py` explicitly prepares body, receptor and appearance
features. Native measurement consumers read retained features; missing appearance
or receptor acquisition cannot trigger an implicit decode inside channel collection.
The four channel observations retain their own original timestamps and unknowns.

`native-stages/hold-geometry.json` contains native geometric holds and unresolved
connections, without sustained-input decisions. `native-stages/processing.json`
and `native-stages/note-types.json` cache per-note pixel measurements independently
of popup ownership and receptor-run association. A HUD refresh change can update
channel assembly without repeating those image measurements.

`hold-state-input.json` captures the geometric bounds, native receptor/body records,
raw HUD refreshes and the geometry scale needed for sustained-state interpretation.
TypeScript `hold_state.ts` returns sustained spans and receptor runs, cached as
`derived-stages/hold-state.json`. This stage never turns hold ticks into separate
presses or invents physical press/release timestamps:

```sh
just derive hold-state .local/data/SOURCE/play/segment-001/hold-state-input.json .local/tmp/hold-state.json
```

Counter and visibility consumers receive compact records, excluding skin image
comparisons and unrelated per-frame detection details. Presentation preparation
uses the retained channel projection when available; legacy traces are projected
one record at a time. Source and frame-count contradictions fail explicitly.

Chart registration saves `ucs-input.json` after reference preparation and chart
projection. It is independent of HTML preparation and supports replaying the complete
UCS draft through the existing `ucs` stage.

Native processing still evaluates the fitted trajectory while inspecting pixels.
The Python callback evaluates returned coefficients or measured displacement;
fitting and model selection run in TypeScript. Source-bound image ownership
verification, including native hold-risk proof preparation, stays with acquisition.
The projection/association consumer cannot invent that proof when it is absent.

Primitive format definitions live in `derived/contracts.json`; Python and
TypeScript compose the same dependencies. Native anchor conventions are shared
with the image producer, rather than copied into an independent consumer version.
The JSON transport retains large integer provenance exactly and decodes UTF-8
across pipe chunks. Physical seconds and coordinates remain floating-point values.

## Validation

`just check` includes TypeScript type checking, direct Node regression tests and
the TypeScript synthetic observation-to-beat-to-UCS matrix.
QG uses native `node-test` integration for `tests/**/*.test.ts`; `pnpm test`
runs the same gate as `just check`. Python retains native acquisition, orchestration
and cross-language boundary tests. Direct tests cover standalone replay without a
Python executable, explicit malformed-input failure, exact section arithmetic,
cross-measure ambiguity and pure HTML rendering. Coordinate snapshot tests cover
promotion, changed producer identity and corruption.
Transport tests exercise multibyte evidence larger than a pipe chunk and original
nanosecond identity. The Node checks also cover zero-time row ordering, unknown
native word states and independent per-event aggregate offset provenance.

Recognition tolerances are retained. Passing these tests does not establish a new
corpus recognition rate. Pixel acquisition, online tracking, native hold/skin
interpretation, source identity verification, metadata/reference I/O and pipeline
orchestration remain Python. Acquisition changes can require frame replay; consumer changes reuse the declared
retained inputs. Native observation refits use a transactional pending segment
before promotion, while ordinary consumer refreshes use their stage artifacts.
See [data flow](play-data-flow.md).
