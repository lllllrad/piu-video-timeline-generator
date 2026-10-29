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
