# Analysis execution contracts

The executable stages separate measurements, visual identities, coordinates,
physical time, musical placement and played-input interpretation. An artifact
is reusable data, not permission to rerun its producer inside a consumer.
`play/analysis.py:finish_play` is the composition root; stage adapters do not
call it or silently acquire missing pixels.

## Producers and outputs

| Producer | Required input | Own output | Excluded responsibilities |
| --- | --- | --- | --- |
| Native observation acquisition | Unchanged recording, source timeline, crop, detector bank | Frame-local candidates, image-role and channel observations with original PTS | Track identity, target times, grades, UCS rows |
| Visual tracking | Frame observations and qualified per-frame coordinate views | `tracking.json`: original-anchor trajectories, fragment identities, source timeline and ambiguity proofs | Receptor crossing clocks, counter/word associations |
| Coordinate measurement and projection | Visual trajectories, original frame comparisons and registered image references | `head-registration.json`: complete native proofs; `coordinates.json`: bound observation and coordinate artifacts | Velocity/time fits, musical rows, input ownership |
| Physical timing | Bound coordinate artifact and its continuous original frame timeline | `physical-timing.json`: relative displacement, clocks, crossing ranges and explicit failures | Song origin, musical rows, popup values, switch effects |
| Native interval validation | Coordinates and physical timing | `native-timing.json`: gap-validation updates and diagnostics | Musical reference preparation, input associations |
| Musical placement | Coordinates, physical timing, native validation and prepared official UCS reference | `beat-input.json`, `beat-result.json`: musical rows and additional reference-conditioned timing proofs | Changing original coordinates or replacing the source-only crossing result |
| Counter association | Final timing view, independent counter events, eligibility intervals | `counter-associations.json`: matches, deferred matches and coverage | Tracking, coordinate registration or fitting clocks |
| Judgment and hold interpretation | Saved words/effects/processing, image geometry and the final timing view | Judgment associations, native hold geometry, timed holds and sustained-state artifacts | Inventing physical switch times, moving chart notes to match inputs |
| Inspection, UCS and rendering | Their explicitly prepared inputs | Inspection artifacts, UCS draft and HTML respectively | Implicit native acquisition or recomputing upstream timing |

Native hold connectivity and timed hold projection are separate producers.
Image connections retain cap/body identities and source PTS even when endpoint
timing fails. Sustained input evidence may authorize UCS hold simplification;
it cannot create or relocate the visible chart.

## Tracking and motion are different questions

Frame assignment measures coordinate views before selecting an identity.
It may consume independently observed frame translations. Final fragment
recovery may reconstruct relative displacement from already tracked positions;
this is an identity proof, not a receptor crossing or musical clock.

A fragment uses certified centers throughout, or one unchanged exact reference
anchor throughout. Fragment candidates with different bases are not joined.
An unsupported or changing basis cannot become comparable because its fitted
trajectory is smooth. Recovery retains original matching-anchor points and
source-fragment IDs; it never inserts observations in a gap. This explicit
relative-motion dependency avoids using physical target times to prove the
identities from which those times will later be calculated.

`NoteTracker.finish` returns visual tracks only. Pre-assignment reference measurements are retained with the tracking output.
Coordinate projection reuses those measurements without reopening frame records
and performs one `skinCenters.projectMany` call. Saved trajectories without
that measurement artifact require an explicit measurement pass. Physical fitting runs its per-track and
shared-motion numerical kernels inside one TypeScript operation; counter
association is called after the final timing view is composed.

## Coordinate and time ownership

The schema-4 `coordinates.json` snapshot contains `track-observations` and
`coordinates` artifacts. Observations own original trajectories, geometry and
source timeline. Coordinates own projected `points` and registration evidence.
They contain no target times, velocity estimates, motion clocks or HUD matches.

The `physical-timing` artifact is bound to those exact inputs. It owns timing
fields and shared displacement but cannot edit positions, lanes or observation
IDs. Native validation binds the coordinate/physical pair. Musical placement
binds that pair, validation and the prepared reference. Composing one view does
not mutate any producer artifact.

Musical references may narrow or recover a timing range under additional
assumptions. That derived range stays in the beat artifact. It never overwrites
the source-only physical artifact. A failed musical placement does not erase
an independently established physical interval. Unsupported or contradictory
measurements remain failures with their original evidence.

Complete conflicting image comparisons stay in `head-registration.json`.
Numerical views retain the measured bounds and compact warnings with an
`evidence_file` reference, rather than repeatedly carrying the complete conflict
lists through coordinate, beat and inspection transport.

Inspection preparation also stores repeated frame-wide tracking ambiguity proofs
once under `evidence/tracking-warnings/<sha256>.json`. Every warning keeps its
reason, note association, times and source PTS; only `candidate_edges` and
`candidate_frame_displacements` move to the referenced, content-verified file.
The inspector links each affected warning to its complete original proof. The
saved analysis and native tracking artifacts remain unchanged. HTML rendering
streams the prepared JSON from a temporary file rather than sending the entire
HTML or an escaped JSON string through the numerical runtime transport.
Inspection composition reads its separately persisted input and result files;
the combined documents do not need to fit in one transport message.

## Execution, reuse and failures

`pipeline-status.json` records actual execution boundaries, start/finish times,
expected outputs and failures in the pending segment. Before a fresh acquisition
creates that directory, its status lives in the sibling
`segment-NNN.build-ID.pipeline-status.json`; successful acquisition moves it inside. A stage is complete only
after its function returns and its declared files exist. Failure preserves
previously published output and names the failed stage; it does not start the
next stage. Whole-segment promotion remains atomic. Overall status remains `running`
between stages; `stage_status: complete` describes only that stage. Only
successful promotion sets `status: published`. A failed promotion retains the
previous report and a failed publication record in the pending directory.

Coordinate capture writes `coordinate-input.json` once at the native producer
boundary. `coordinates.json` is the independently reusable coordinate output.
The subsequent file graph is:

| Stage | Files loaded at entry | Output |
| --- | --- | --- |
| Physical timing | `coordinates.json` | `physical-timing.json` |
| Native interval validation | `coordinates.json`, `physical-timing.json` | `native-timing.json` |
| Reference preparation | `beat-reference.json`, the three preceding outputs, available official UCS | `beat-input.json` |
| Musical timing | `beat-input.json` and all dependencies it names | `beat-result.json` |
| Timing read model | Musical timing inputs and `beat-result.json` | `timed-view.json` |

`beat-input.json` is a schema-2 descriptor with file names, byte identities and the
prepared official reference. It does not duplicate observations or UCS contents.
Each adapter loads all declared files into one invocation-local `InputFiles`
snapshot before calculation. Repeated accesses reuse its buffers and parsed
values. Loading closes before the numerical kernel runs; undeclared inputs fail.
The numerical kernels receive data, not paths, loaders or callbacks that open
files. Private work arrays are local to that calculation. They are not the
transport or persisted contract of another stage.

Python orchestration passes the segment directory and retains acquisition
metadata. It neither receives nor resends coordinate/physical/native arrays.
Only the explicit downstream read-model boundary loads `timed-view.json` once
for counter/judgment and native hold consumers.

`file-stages/<stage>.json` binds producer implementation, normalized input byte
identities and output identity. Input identities use already loaded buffers;
checking reuse does not reopen the files for parsing. Cache hits leave output
files untouched. Changed dependencies invalidate reuse; damaged manifests or
reused outputs fail explicitly. Inputs changing while loading or calculating also fail.
Segment-local prefixes normalize to `@segment/` for promotion. A shared
implementation dependency can invalidate multiple consumers together.

Replay one producer without upstream recomputation:

```sh
just derive-file physical-timing .local/data/SOURCE/play/segment-001
just derive-file native-timing .local/data/SOURCE/play/segment-001
just derive-file musical-timing .local/data/SOURCE/play/segment-001
just derive-file timed-view .local/data/SOURCE/play/segment-001
```

Missing inputs fail; a consumer never acquires pixels or invokes its upstream
producer. These commands do not publish a report or register a chart.

## Feasibility and validation limits

Tracking needs displacement, but it does not need the later physical crossing
clock. Separating relative identity evidence from absolute target-time inference
makes this ordering executable without a timing/association feedback loop.
Image persistence can depend on a physical movement model; its native feature
acquisition remains separate from that model-conditioned interpretation.

Synthetic tests cover source-only fitting at multiple resolutions/frame rates,
repeated captures, chords, explicit failures, unchanged coordinate ownership,
foreign-input rejection and physical-cache integrity. Native integration tests
exercise acquisition followed by explicit coordinate/timing/association calls.
They do not establish a corpus recognition rate or a wall-clock performance
budget. Costs still depend on observed candidate counts and trajectory density;
large inputs need measurement, rather than an assumption that saved data is cheap.

Native interpretation streams retained JSONL observations and validates the
exhausted frame count. Clearance and body-risk producers consume frames directly.
Hold geometry first projects every image comparison to exact compared-row spans
for its declared reference objects and retains the exact role proofs consumed by
the role join. Channel collection retains popup scalars, motion positions and the
same role proofs. Repeated note queries use these consumer views, rather than
reparsing full search alternatives from disk. Native traces keep every original
comparison and timestamp; these in-memory views do not overwrite acquisition or
add a decoded-media cache. Regression tests compare complete geometry, warnings
and role evidence against consumers operating on unprojected observations.
Memory depends on the consumer view and derived output, not the complete native
search trace.

The JSON transport protects unsafe integer tokens before ordinary parsing,
preserving exact provenance without V8 reviver source contexts for every field.
Markers cannot collide with source strings; malformed JSON and nonfinite values
fail. A bounded-heap regression covers large records and integer/escape handling.

### Reusable tracking inputs and untimed hold shapes

`tracking-observations.json` retains per-frame positive detections, qualified
coordinate views and original PTS before track identity is assigned. Its digest
binds source media, crop, window, layout, skin and coordinate contracts. Replaying
identity assignment can reuse these positions without decoding video. When
projecting compatible saved measurement records into this input, the adapter
explicitly discards previous track IDs, targets and statuses; changed acquisition
or coordinate contracts require new measurements.

Hold interpretation exposes `observed_holds` independently of timed `holds`.
Each connected shape retains its image connection, component IDs, observed frame
extent and nullable endpoint ranges. A failed endpoint clock keeps the shape,
emits its timing warning and suppresses duplicate tap components. The inspector
lists these shapes and overlays only their positive per-frame image intervals;
it does not invent target positions for an untimed shape.

### Serialized stage reuse

Image-interval projection uses `hold-intervals-input.json`, `hold-intervals-output.json`
and `hold-intervals.stage.json` to bind image geometry to saved timing stages.
The sustained-state producer stores `hold-state-input.json`,
`hold-state-output.json` and `hold-state.stage.json`. Its manifest binds producer
code, geometry/event parameters and the serialized coordinate, physical timing,
beat, hold-frame and image-geometry artifacts. Cache lookup checks those file
identities before assembling the input. An unchanged stage neither rebuilds nor
rewrites its request and does not send observation objects through the worker
transport. On a miss, the adapter persists the minimal timing view once and the
TypeScript producer consumes that file and writes its output once. Input/output
corruption fails explicitly; changed dependencies invalidate reuse. File identity
hashes stream existing bytes with segment path prefixes normalized, preserving
identity through pending-directory promotion without parsing and re-encoding JSON.

Native type/processing producers also keep small file-reference receipts before
building or hashing a composed request; receipts bind the existing producer
artifact bytes and do not replace its provenance.

Hold and judgment association and channel contracts reference the saved note-stage artifacts
instead of reserializing the full composed note view. Channel assembly can reuse
unassigned popup/motion rows when acquisition identity, original frame timeline
and native file signatures still agree. Track-dependent type/processing artifacts
keep their own bindings; a type-cache miss acquires the required native role view.
Changing track identity cannot silently reuse another track's type assignment.

Inspection source and native preparation are persisted independently as
`inspection-source.json` and `inspection-observations.json`. Input capture and
preview pass paths and produce `presentation-input.json`,
`interpretation-result.json` and `interpretation-view.json`. Repeated tracking
connection references and alternatives remain in content-addressed evidence files;
read models retain verifiable links instead of duplicating complete proof graphs.
Inspection preparation consumes `presentation-input.json` directly and writes
`inspection-result.json`; production rendering consumes `report-data.json`
directly. The worker boundary carries paths. Direct calculation APIs remain
available for synthetic cases. Coordinate, physical, native and beat production
use the file graph above; inspection and hold interpretation retain their own
explicit input artifacts.

Progress records distinguish role clearance, hold frames, image geometry,
sustained state, native risk and channel assembly. A parent stage preserves its
children's completion/failure records; only atomic publication marks the report
published.
