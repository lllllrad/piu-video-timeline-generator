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

The schema-3 `coordinates.json` snapshot contains `track-observations` and
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

The physical cache is `derived-stages/physical-timing.json`. Its key includes
the bound coordinate input and the transitive TypeScript implementation graph.
Changed physical algorithms reuse coordinates. Changed popup data or song
references do not enter the physical input. Counter-reader-only changes refresh
`counter-events.json` while reusing saved coordinates. Musical calculation has
its own `derived-stages/musical-timing.json` cache keyed by the prepared beat
request; counter events do not enter that request. A damaged cache fails explicitly;
it is not silently replaced by a fresh calculation. As with other derived
stores, a shared implementation dependency can invalidate several consumers.

Replay the physical calculation without video, OCR, Python or musical data:

```sh
just derive physical-timing COORDINATE_ARTIFACTS.json PHYSICAL_RESULT.json
```

The input is the `output` pair from `coordinates.json`: `observations` and
`coordinates`. The output adds `physical_timing`; it is suitable for subsequent
native interval validation. Standalone execution does not publish a report or
register a chart. Existing observation artifacts remain reusable; there is no
media or chart migration.

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
