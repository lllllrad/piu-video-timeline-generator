# Derived analysis runtime

Saved observations are ordinary data, independent of the acquisition language.
Python owns video decoding, image measurements, OCR, audio alignment, downloads
and acquisition orchestration. TypeScript under `src/piu_timeline/derived/` owns
joint coordinate registration, saved-track and clock fitting, native spacing and
chord checks, common song-phase and beat-row reconstruction, speed estimates,
exact UCS timing and per-measure row transcription, and HTML rendering.
It also owns popup/row association and recovery, hold chart projection, concrete
visibility/counter effects, input ranges, continuity and unresolved-evidence
diagnostics. Original visual observations are inputs to these operations.

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

`report-data.json` is the prepared presentation document. `play/presentation.py`
owns policy projection and diagnostic preparation; `play/report.py` only renders
that data through TypeScript. Rendering preserves opaque serialized acquisition
metadata and escapes HTML/script delimiters. It does not run timing inference.
`report-summary.json` supplies the index without repeating projection or reading
every trajectory. Render a prepared report using TypeScript alone:

```sh
just render .local/data/SOURCE/play/segment-001/report-data.json .local/data/SOURCE/play/segment-001/report.html
```

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
the existing Python synthetic observation-to-beat-to-UCS matrix, which now calls
the TypeScript implementation. Direct tests cover standalone replay without a
Python executable, explicit malformed-input failure, exact section arithmetic,
cross-measure ambiguity and pure HTML rendering. Coordinate snapshot tests cover
promotion, changed producer identity and corruption.
Transport tests exercise multibyte evidence larger than a pipe chunk and original
nanosecond identity. The Node checks also cover zero-time row ordering, unknown
native word states and independent per-event aggregate offset provenance.

Recognition tolerances are retained. Passing these tests does not establish a new
corpus recognition rate. Pixel acquisition, online tracking, native hold/skin
interpretation, source identity verification, metadata/reference I/O and pipeline
orchestration remain Python. Not every producer has an independently persisted
output yet; native detector/geometry changes can still require frame replay.
See [data flow](play-data-flow.md).
