# Derived analysis runtime

Saved observations are ordinary data, independent of the acquisition language.
Python owns video decoding, image measurements and geometry, source-bound image
proofs, OCR, audio alignment, downloads and acquisition orchestration. TypeScript under `src/piu_timeline/derived/` owns
coordinate-based frame assignment, joint coordinate registration, saved-track and clock fitting, native spacing and
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

Before trajectory identity is assigned, `play/skins/frame_centers.py` measures
each positive image comparison independently. It exposes a certified cap-center
interval when available and an original matching-anchor interval scoped to its
exact reference identity. Both use analysis-image pixels with y downward.
`derived/frame_tracking.ts` predicts in one compatible coordinate view at a time;
raw origins from different references cannot substitute for cap centers.
When positive alternative comparisons cover the same cap pixels, their separately
scoped anchors are retained too. A changing representative can link through a
shared exact reference; all shared views must agree. This does not certify an
absolute center for an unregistered image.

Frame assignment retains only links required by every maximum-cardinality
matching. Co-observed, separated positions in a common basis establish note order;
asynchronous or incomparable positions do not establish that order. Missing
observations cannot make a following note inherit another identity through a
wide proximity threshold. Ambiguous fragments are kept separately with
`ambiguous_note_tracking`, original timestamps and candidate pixel positions.
Later coordinate refitting preserves these warnings. Co-observed compatible image
positions in at least two lanes can independently measure one common signed frame
translation before identities are selected. Equal competing translations remain
unavailable. Without that measurement, association uses a speed bound in both
directions; past velocity cannot prohibit a new stop, acceleration or reversal.
These identity bounds do not establish a clock or enlarge chart target ranges.
Signed frame steps retain endpoint error intervals and can carry a disappeared
cap forward through the observations of other caps. A gap breaks that chain;
there is no interpolation over missing steps. A final unmeasured capture step
retains its full speed bound. A visibility gap over 50 ms without a displacement
chain needs at least four repeated, compatible positions; their measured errors
and one capture-step allowance bound a trajectory prediction. A lone position
cannot establish a reversal and return to the field. Only forced identities may supply a subsequent
single-cap step in a compatible coordinate view, after the assignment has been
decided independently.

Tracking appends original matching anchors to the immutable detection trajectory.
The independently measured centers guide association and are projected into the
later coordinate fit through their source-bound records. Counter values, judgment
words, switch effects and the musical grid are absent from frame assignment.

`coordinates.json` stores a schema-2 source-bound snapshot containing two schema-1
artifacts: `track-observations` (original detection trajectories and geometry) and
`coordinates` (registered trajectories, clocks and physical timing attempts).
It excludes popup events, matches and coverage. Its fingerprint binds it to source
identity, geometry, detector and upstream timing contracts.

`derived/stages/contracts.ts` declares these immutable artifacts and owned fields.
The acquisition adapter in `stages/coordinates.ts` constructs them. Numerical
kernels use private mutable work arrays; public results contain indexed updates
restricted to owned fields. Changing an observation ID, lane, trajectory or
another stage's fields fails explicitly. Composition constructs fresh read models
without modifying producer artifacts.

Bound results contain an `input_fingerprint` in addition to their stage and data.
Coordinate results bind their observation artifact; physical timing results bind
the narrow pair of observation and coordinate artifacts. Beat results bind the
complete beat request, including reference timing and preparation. Inspection and
interpretation results bind the complete prepared presentation request. Composition
checks these bindings and rejects results from another input, even when note IDs
and counts match. These input bindings complement stored output hashes and producer
identities; they do not replace them.

An optional explicit `artifact_root`, ending in `/`, identifies the segment
directory. `derived/fingerprint.ts` replaces that exact string prefix with
`@segment/` while hashing, so pending-directory promotion preserves input identity.
Other paths and input values remain part of the fingerprint.

`native-timing.json` records physical interval validation before musical fitting.
`beat-input.json` has schema 1 with `observations`, `coordinates`, `native_timing`,
`reference`, `timing_text` and optional `preparation`. The reference contains the
verified song origin and uncertainty or an explicit unavailable reason. The stage
does not fetch timing files or prepare audio alignment. `beat-result.json` is a
`beats` artifact: owned timing updates, musical diagnostics and independent native
recovery diagnostics. It contains no acquisition identity or input associations.
`beats.materialize` explicitly combines results for downstream readers.
Nanosecond file timestamps remain outside numerical calculations.

Counter association accepts only lane, status, target, uncertainty and exclusion
reason fields alongside counter events and eligibility intervals. Its
`counter-associations` artifact contains event interpretation, matches, deferred
matches and coverage. Judgment association returns a separate
`judgment-associations` artifact, saved as `judgment-associations.json`.
Neither stage returns coordinate edits. Raw frame/HUD observations remain separate.

When independent neighboring beat rows establish a native coordinate model,
spacing validation checks each observed head against that model's position and
existing native/reference error bounds. Each contradicting head is attributed
separately. Opposite permitted endpoint errors can change their relative gap;
the gap cannot reuse a single-coordinate error budget. Conversely, equal shifts
of both heads preserve their gap but still contradict the reference coordinates.
Without an independent model, the registered-motion gap check remains required.

Reference-coordinate models retain the complete feasible region of positive
velocity and intercept values. Every reference must satisfy the existing
lane-relative reference error bound; no outlier is discarded. A median line is
only a representative and cannot invalidate another feasible line. The stored
convex region also prevents choosing a convenient line to force one beat row.
Target-time ranges include all feasible models and the measured head's positional
bound. Beat-domain filtering and native recovery consume these complete ranges.
Independent pair validation requires one common model for both heads; separate
possible models for each head do not establish a consistent pair. If the model
can include zero/reverse velocity, inverse timing is not identifiable and fails.
Missing model bounds fail explicitly instead of reverting to a point estimate.

Before subdivision selection, `beats/gaps.ts` measures co-observed endpoint
intervals in one qualified coordinate system. A common positive clock must cover
both native target intervals. Its residual and endpoint errors bound velocity;
dividing the measured gap by that velocity interval bounds the difference between
beat rows. Interval propagation removes incompatible row combinations before a
split can win. An object without any candidate row cannot calibrate independent
neighbors. Source gaps, PTS, clock bounds and row differences remain in the beat
artifact. Unsupported clocks or image origins supply no such constraint and
retain the existing explicit diagnostics.

`derived/native_gaps.ts` validates source gap failures against acquired image-cap
measurement errors before musical reconstruction. Every co-observed endpoint
needs a qualified native center, declared registration uncertainty and matching
original PTS. Intersect all observed gap intervals, propagating both endpoints'
errors; a passing median cannot erase a contradictory frame. A qualified source
clock rejected only by explained gap checks retains its original target, with
additional calibrated position error propagated into its time uncertainty.
Other failed native checks and unsupported clocks keep their warnings.

The same interval comparison applies to later registered-gap checks. When target
times change, propagate the qualified shared clock slope error into a prediction
interval and compare that interval with the acquired gap intersection. Prediction
uncertainty cannot repair an empty intersection of acquired measurements. Independent
absolute coordinate models retain their separate bounds. Missing measurement
proof does not enlarge the existing fallback tolerance. Native resolutions and
original warnings remain in `timing_reconstruction.native_gap_validation`.
This component does not require a musical reference. A restored native interval
can trigger reassociation while beat verification remains explicitly unavailable.

A confirmed tap can retain its independently restored native crossing interval
when musical-row assignment fails. The presentation/association view marks it
with `target_timing_basis: native_motion` and `chart_timing_status: unresolved`;
its midpoint is a recording-time estimate, not an accepted beat row. This requires
an exclusively tap image role, a finite native interval and a restored native
clock. Unknown/conflicting roles, hold caps, failed clocks and unrelated exclusions
cannot use this path. Original source exclusions and beat failures remain intact.
Normal refresh ownership and independent input-evidence requirements still apply.
UCS transcription reports the unresolved beat placement and neither places the
tap nor extends timing sections to accommodate it.

The same separation applies when a failed motion clock is replaced by a bounded
native-coordinate interval. A unique musical row is not required to retain that
continuous interval. Conflicting coordinate models, failed joint validation or
changed/finally excluded reference rows cannot supply it. Native timing recovery
and musical placement have separate statuses and warnings; an unresolved musical
row stays excluded from UCS even when independent input evidence uses its native
interval.
If a coordinate candidate fails its final native pair/concurrency check or a
reference fails validation, discard that candidate's timing interval. A separately
restored source motion clock or frame-bound crossing can retain its own interval,
stored in `source_timing` on the recovery proof before promotion. Its
`independent` flag requires a restored source clock/range, rather than a previous
coordinate-derived interval. Failed source attempts remain available for review.
Restore its original range and fit method together. The musical row remains
failed, and the warning records the rejected coordinate derivation. Without an
independent source interval, mark native timing failed so image geometry and
association consumers cannot use the rejected range. Source observations remain
available for review.

Replay a prepared input without Python, OCR or video decoding:

```sh
just derive beats .local/data/SOURCE/play/segment-001/beat-input.json .local/tmp/beats.json
```

The same command supports `native-gaps`, `coordinates`, `clocks`, `speed` and `ucs`:

* `native-gaps`: schema 1 with `observations` and `coordinates` artifacts. A
  `beat-input.json` supplies these fields too; musical reference fields are unused.
  Output is a `native-timing` artifact before musical-row fitting.
* `coordinates`: `tracks`, `timeline`, `height`, `spacing`, `receptor`, `bottom`.
  This invokes the registered-track solver and returns its numerical result;
  it does not construct the source-bound `coordinates.json` snapshot or its
  observation/coordinate artifacts. That boundary belongs to
  `stages/coordinates.ts` and the Python `play/stages.py` persistence adapter.
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

`presentation-input.json` has schema 2. Its `source` separates tracks, judgment
associations, hold evidence, chart context and visual channels into named immutable
artifacts. Passive `metadata` is reattached when composing the read model and does
not enter numerical inference. `observations` contains prepared frame records,
named HUD occluders and verified image-risk proofs. Native preparation retains its
own source-bound caches. Configured-motion measurements also carry the exact
interpreted geometry and source identity used by their native producer.
The association scope is tagged `inspection-associations`; it contains the
inspection's collected association inputs and is distinct from the narrower
`judgment-associations` calculation result.

`presentation.prepare` returns an ordered `inspection` artifact, saved as
`inspection-result.json`. Each consumer owns a whitelist of fields. Hold
projection expresses note changes as indexed updates and added derived chart
objects. Other consumers cannot rewrite trajectories or add chart objects.

| Stage | Inputs | Output |
| --- | --- | --- |
| `hold-view` | Tracks, native holds, channels and prepared risk proofs | Hold-aware chart objects and judgment associations |
| `motion-effects` | Concrete chart effects | Pause and relative-speed models |
| `configured-processing` (optional) | Already prepared native processing measurements bound to interpreted geometry and motion | Measured processing channel supplied before effect interpretation |
| `effect-view` | Interpreted rows, lane/processing evidence and chart effects | Effect-specific associations and visibility interpretation |
| `policy-view` | Interpreted chart and scoped policies | Eligible input associations |
| `timing-ranges` | Targets, input observations and compact counter frames | Target/input ranges and explicit unknowns |
| `visibility` | Native positions, models, HUD geometry and processing states | Explained occlusions, detection gaps and motion warnings |
| `diagnostics` | Original/projected notes, ranges and continuity results | Excluded-track and unresolved-evidence warnings |

The seven calculation consumers cache owned outputs under `derived-stages/`, keyed by consumed
inputs and implementation dependencies. The manifest records input/output hashes
and which results were reused. Unrelated metadata, such as a title, does not
invalidate inference. Shared contract or pipeline-composition changes can affect
several consumers. Corrupt outputs fail explicitly. Segment-local references use
`@segment/` inside hashed artifacts so directory promotion preserves their identity.
Maintenance checks include producer identities and retained source-file signatures.
The optional `configured-processing` stage occupies the position shown in the
table but reuses its native measurement cache instead of running a `Store`
consumer. Inspection preparation validates those measurements against the
interpreted geometry and source inputs; it cannot request new pixels.

Replay the prepared calculation without Python, image libraries, audio, network or
source video:

```sh
just derive presentation .local/data/SOURCE/play/segment-001/presentation-input.json .local/tmp/inspection-result.json
```

For `inspection-view`, supply a JSON object containing `request` (the prepared
presentation input) and `result` (the inspection artifact). It composes the
`report-data.json` read model. Incomplete, duplicate and out-of-order consumer
results fail explicitly. Normal orchestration saves both artifacts before
calling the renderer.

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

UCS generation separates visible geometry (`charts/draft.ts`), automatic hold combo
observations (`charts/combo.ts`) and the union of independent draft contributions
(`charts/merge.ts`). Combo annotation cannot edit visual endpoints. Draft merging
uses exact song-relative UCS times and rebuilds measure grids, retaining source
claims and explicit conflicts. See [chart data](chart-data.md#hold-combo-row-extension).
