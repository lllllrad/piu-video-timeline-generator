# Recognition validation

Establish expected behavior with independently generated scenes before using
recordings to evaluate a recognition change. A passing collection of regressions
does not establish that ordinary gameplay is supported. The current suite has
substantial consumer coverage, but does not yet establish complete ordinary
image recognition across the supported skins and four visual channels.

## Test inputs and expected results

[Basic recognition cases](recognition-cases.md) defines the support target and
expected outcomes before generator or processor changes. Its cases are behavioral
requirements, not a list of passing tests.

Specify chart objects, their movement, held states and independent channel events
as ground truth. Sample that truth into pixels or saved native observations.
Expected objects, timing bounds and warnings must come from the scene definition,
not from the recognizer's output. Do not use chart targets as physical press times.
A hold is one sustained object; its visible leading cap is not an extra press.

Use three boundaries:

1. Generated RGB frames through native measurement: check object roles, retained
   coordinates, occlusions and original recording time/source PTS.
2. Generated stored observations through actual derived consumers: check clocks,
   channel ownership, held intervals, warning behavior and UCS placement.
3. Native measurements through the actual consumer input projection: check that
   required evidence survives storage and stage boundaries. Separate successful
   producer and consumer unit tests cannot establish this connection.

## Required scenario families

Each family needs successful cases, contradictory evidence and insufficient
evidence. For ambiguity, assert the explicit unresolved result or warning and
absence of an invented note, input or timing bound.

| Family | Required variations | Current validation limit |
| --- | --- | --- |
| Object appearance | Tap, short/long hold, start/body/end, adjacent holds, extra independent tap, empty lane | Geometry/role cases exist; a broad RGB skin matrix is missing |
| Rows and lanes | Single/Double, chord, partial chord, close stagger, dense same-lane rows | Stored-observation matrix exists; equivalent RGB combinations are incomplete |
| Geometry | Multiple image sizes, lane spacing, crop offsets, fractional anchors | Derived scaling cases exist; native skin/layout combinations are incomplete |
| Capture | 30/60/120 fps, render repeats, dropped frames, irregular capture gaps | Stored-observation cases exist; pixel-level combinations are incomplete |
| Visibility | Judgment/combo foreground, white effects, body-only remainder, disappearing/reappearing cap, image boundaries | Individual tests exist; hold-cap pixel tests cover body remainder, missing cap and white flash, not every occluder |
| Input evidence | Popup only, light only, disappearance only, agreeing/conflicting combinations, no evidence, MISS | Independent channel tests exist; a complete combined pixel scene matrix is missing |
| Hold semantics | Body continues after cap passage, tail passes without tap, short holds, held ticks without new press | Native integration and cap-to-consumer tests cover selected cases, not every skin |
| Motion | Constant speed, abrupt/gradual speed change, stop, reverse | Consumer diagnostics exist; unsupported motion must remain explicit |
| Storage | JSON round trip, missing channel, stale contract, foreign source PTS, selective replay | Stage-boundary tests exist; new evidence fields still require projection tests |

These are validation obligations, not claims that every row is complete. Add
bounded combinations of interacting factors, especially hold appearance with
occlusion/capture gaps and chords with missing/conflicting channels. Avoid a
large Cartesian product of unrelated options that adds cost without testing an
interaction.

## Connected native scene checks

`tests/derived/recognition-scenes.test.ts` supplies chart objects to
`tests/play/skins/scenes.py`, which independently renders their caps and bodies
and runs the real RGB detector, tracker, role join and image-connection consumer.
The expected objects come from the TypeScript scene definitions. No target times
or object identities are supplied to acquisition. Temporary reference banks use
the same declared glyph design, with separate cap/connection/clearance regions;
frames vary position, background noise, lane count, integer scale and cadence.
Independent in-memory RGB scenes run in up to four processes with fixed seeds
and ordered results. Encoded scenes run serially to bound FFmpeg thread pools;
parallel execution does not change their native frame order or expected results.

The native matrix has 86 scenes: empty fields; isolated taps in all five lane
kinds; Single/Double chords; staggered and repeated taps; long/short holds versus
two taps; adjacent holds; real taps before/after holds; overlapping lanes;
unobservable connections; orphan bodies; and contradictory tap/hold observations.
It checks exact cap counts/positions/roles in each clear frame, original PTS,
unique hold ownership, and explicit unknown/conflict or orphan-body diagnostics.

This is native-boundary coverage for parts of O01-O08, O10-O13 and O15-O17.
It does not establish their clocks, final held/input semantics, warning projection
or UCS output. Nor does it establish O09/O14/O18, realistic skin variation, named
foreground combinations or the complete visibility/capture/channel matrix.

The matrix includes 0.5/1/1.5/2 scales and additional 1.25 and 4/3 short-hold,
two-tap and adjacent-hold controls. Native coordinate acquisition consumes the
same actual image comparisons. These cover the observed whole-frame sampling
phase failure without changing reference error limits. Separate sampling tests
compare source-cell areas with full-frame OpenCV resizing, exclude unsupported
source rows and require complete same-lane cap support for body subfeatures.
T05 remains incomplete for arbitrary crop origins, independently rounded axis
scales, perspective and the downstream timing/UCS boundaries.

`tests/derived/encoded-recognition.test.ts` adds 26 encoded-source scenes. It
creates lossless FFV1/NUT recordings, preserves a nonzero source offset, and runs
the actual `decode_frames` path with FFmpeg's default scaling at 0.5/1.5/2 sizes.
The oracle reads independent ffprobe frame integers and time bases. Assertions
cover every cap, exact lane/role, persistent track, type join, native coordinate
source PTS, hold ownership and per-frame connection evidence. Source bytes and
mtime must remain unchanged. Cap-only reference controls retain unknown type
instead of inventing a tap or hold. They use the shared glyph interior, excluding
role-dependent edge interpolation. The ordinary references include declared
source context beyond comparison regions; context never becomes geometry.

Kernel checks separately cover known decoder coefficients, negative-tap alpha
holes, explicit context extraction and unavailable support. This establishes
the tested decoder/measurement boundary, not lossy codec/chroma variation,
arbitrary background/skin animation, full timing, input association or UCS.

## Promotion order

For each processor change, first reproduce the failure in a generic synthetic
scene and add neighboring positive/negative cases. Pass its pixel, consumer and
stage-boundary checks, then the full `just check`. Only then replay the focused
recordings to look for scene assumptions absent from the generator. Generalize
new findings into the generator before expanding corpus replay.

Ordinary support is not established while required combinations have unknown
behavior. Keep gaps visible and prioritize them over collecting more examples
of an already understood failure. Scope unsupported skins/modes explicitly;
never silently treat them as ordinary successful recognition.

Recording review measures generalization. Warning totals alone do not measure
accuracy: retain raw observations, compare missing/extra objects and evidence
ownership, and independently reconcile result grades where available. Song
mechanics belong in the separate chart repository; recordings and diagnostics
remain ignored local data.
