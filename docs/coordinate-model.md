# Coordinate frames and stage inputs

Coordinates have both a screen frame and an anchor convention. Sharing pixel
units does not make two anchor conventions comparable. Qualification belongs to
the measurement producer; a smooth trajectory, beat row or input match cannot
establish it.

## Screen and time frames

| Quantity | Units and origin | Conversion owner |
| --- | --- | --- |
| Layout lanes, receptor and native detection `x`/`y` | Fraction of the analyzed game crop; top left, y downward | Native screen/detector adapters multiply by analysis width/height |
| Original track positions | Analysis-image pixels; game-crop top left, y downward; recording seconds | Detection adapters retain the image-template anchor |
| Projected cap centers | The same analysis-image pixel frame; independently measured cap-center anchor | `play/head_registration.py` and `derived/skins/centers.ts` apply batched registered projections without timing fits |
| Reference image anchors and center uncertainty | Original reference-image pixels | `play/skins/coordinates.py` uses the actual vertical reference scale and sampling origin |
| Scroll phase and fitted head offset | Analysis pixels in a motion chunk; `head_offset = image_y + phase` | `derived/registration.ts`; offsets from different chunks have no common origin |
| Native frame PTS | Original media stream time | Acquisition retains it beside recording time; consumers check the saved timeline |
| Note targets and input brackets | Original recording seconds | Separate motion/beat and visual-input consumers; an input bracket cannot move a chart target |
| UCS timing | Song-relative beats/rows and seconds | Verified audio translation and official UCS tempo sections; no media retiming |

Analysis resolution is not fixed. Pixel quantities must be interpreted with the
saved dimensions and lane spacing. A localized raster center is a point in the declared reference convention.
Candidate scatter and an assumed continuous translation do not create a spatial
radius. Independently measured source-geometry bounds belong to their own
measurement producer; they cannot be added automatically to raster localization.
Geometric cap centers do not establish engine timing anchors or capture latency.

Image-reference scale uses a bank's explicit full-game `reference_frame` when
the source and analysis grids have a uniform transform. Identical grids preserve
native reference pixels, regardless of small rounding differences in HUD lane
spacing. Banks without this declaration and nonuniform transforms use the
existing lane-spacing model. Acquisition, registered image anchors and hold
coverage use the same scale reader; no consumer chooses a scale from input or
beat timing. See [reference search](note-skin-images.md#reference-frame-and-comparison-budget).

## Trajectory views

The stored note fields retain different responsibilities:

* `detected_points` holds original image anchors when registration produced a
  separate fit trajectory.
* `points` holds the trajectory used for motion and timing fits. It can contain
  centers, unregistered matching anchors, or native silhouette measurements.
  Its name alone never qualifies a cross-track distance.
* Before a separate detection trajectory exists, original `points` is also the
  detection trajectory. This storage selection is centralized; consumers do not
  implement their own fallback expressions. A projected fit with missing original
  points is rejected rather than used as image evidence.

TypeScript `coordinates/points.ts` exposes `detectionTrajectory` and
`fitTrajectory`, returning distinct, read-only purpose-tagged views with an
explicit image frame and vertical axis. Python `play/observations/coordinates.py`
selects the corresponding stored fields for native adapters. Selection does not
apply an offset or resample points. The relative-motion entry point requires a
`Trajectory<'fit'>` and rejects an image-ownership view at runtime as well as in
its TypeScript input type. A displacement uses the fit trajectory; matching an
image region to an identity uses the original detection trajectory.

## Measurement qualification

`coordinates/measurements.ts` is the shared reader of image-registration wire
fields. Numerical consumers and Python native adapters use the same reader,
including batched calls across the native/TypeScript boundary. It returns one
of these explicit kinds:

| Kind | Meaning | Permitted use |
| --- | --- | --- |
| `native_cap_center` | Source registration and a uniquely localized current position agree | Bounded center distances and independent references, subject to each consumer's ordinary limits |
| `image_reference_anchor` | Original image-matching origin | Relative distances only when both origins use the identical reference |
| Conflicting localization | Distinct sampled-image positions have indistinguishable comparison scores | Explicit failure; no center projection, encompassing interval or independent measurement |
| `unavailable` | Missing, contradictory or unsupported registration | Explicit failure with a reason; no assumed center |

`coordinates/trajectories.ts` checks the complete fit trajectory and source PTS,
then supplies its coordinate basis to spacing/reference preparation. An omitted
coordinate method is unavailable. A `registered` status alone cannot establish
an origin. Native silhouette producers explicitly declare
`native_cap_measurements`. Partial image projection cannot mix centers and raw
origins into one trajectory. A same-reference fallback cannot equate a projected
center with the original matching anchor, even when center uncertainty is large.

## Stage consumers

| Consumer | Position input | Qualification and output |
| --- | --- | --- |
| Image ownership, role reads, masks and cap/body connectivity | Detection trajectory and native image bounds | Preserve exact original frame/image identity; do not consume beat targets |
| Image-motion fallback for temporal body joins | Tagged fit trajectory | Same observed identity across adjacent original frames; registered displacement remains a separate relative-motion input |
| Generic motion/clock fitters | Fit trajectory | Fit motion; fitting does not certify the anchor convention |
| Beat spacing and coordinate recovery | Fit trajectory plus explicit trajectory basis | Compatible centers or identical raw reference origins; unknown origins cannot veto certified neighbors or anchor recovery |
| Native chord and endpoint-gap checks | Shared typed per-frame measurements | Enforce center/reference distinction, endpoint errors, duration and original PTS |
| Rigid hold-length checks | Fit endpoints plus shared typed measurements | Every accepted endpoint error comes from the common center reader |
| Native body-risk ownership | Raw anchor for image-component ownership; certified center for approach bounds | Check the two positions separately; neither substitutes for the other |
| Visibility and duplicate-image ownership | Detection trajectory | Fit coordinates cannot replace original image positions |
| Motion warnings | Fit trajectory | Pose-dependent raw matching origins do not replace the motion producer's coordinates |
| Judgment association and UCS transcription | Derived timing ranges and independent visual evidence | Consume position-derived timing; do not reinterpret image anchors or feed input times into beat reconstruction |

Wire JSON remains extensible provenance. Typed coordinate views are constructed
at calculation boundaries; they are not a claim that every stored numeric field
is statically branded. Low-level numerical fitters operate on supplied points
and cannot qualify cross-track coordinates themselves. Registration readers and
stage entry checks enforce that responsibility. Cache contracts for affected
consumers change with this model; retained frames remain reusable.

## Bounded native timing without a common clock

Certified cap endpoints supply displacement intervals using both declared
endpoint errors. `derived/tracks.ts` intersects those intervals; contradictory
certified movements remain warnings with the original PTS and rejected bounds.
Unknown reference origins cannot outvote a certified measurement.

A short final observation block may lack enough support for a common affine
clock. `derived/native_clock.ts` then retains all positive constant-speed models
consistent with the same cap's measured centers, reference errors and original
capture intervals. Repeated image positions widen the capture interval. Missing
detector observations do not create missing source frames. If the final detector
block is too short, earlier positions of the same identity can contribute while
the original source timeline remains continuous. Reverse or curved
motion, contradictory native steps, source gaps and extrapolation beyond the
bounded recording support fail explicitly.

Original frame PTS does not identify the center of a game-render capture phase.
Each isolated source observation retains one adjacent original frame interval on
either side. A fixed half-frame assumption can exclude a valid musical row even
when native position errors are small. Repeated positions extend that capture
interval without moving timestamps. The complete feasible crossing domain must
still satisfy the source-coverage and extrapolation limits; an overwide domain
fails instead of retaining only convenient models.

The extrema of the feasible models bound the receptor crossing; a representative
model only supplies a display position. This result keeps a
`shared_subframe_clock_unresolved` warning and its own `native_interval_model`;
it does not acquire a shared phase or clock. Musical rows still require their
ordinary independent validation. Processing compares all feasible integer image
alignments before declaring absence, and possible positions remain bounded when
checking passage or disappearance. Beat targets and input times do not move the
native position domain.


A uniquely supported translation across independent lanes can preserve image
identities through an unusually large captured step. A one-frame translation is
preferred when independent lanes support it throughout their recent displacement
intervals, including one observed render step of capture-phase uncertainty.
Otherwise the search covers the declared maximum capture interval. Each possible
translation uses its own complete matching; only links forced under every
hypothesis survive. A guessed terminal step cannot replace measured displacement
through a long visibility gap when repeated native positions constrain that gap.
The observed render-step allowance covers both the historical velocity interval
and the future endpoint of a visibility-gap prediction.

Oversized steps retain original timestamps and explicit
`observed_frame_step_exceeds_source_cadence` / `native_motion_cadence_unresolved`
warnings. They supply measured screen displacement while leaving engine time and
the distinction between capture delay and scroll effects unresolved.


Physical timing summaries count per-note reconstruction states. A restored
interval with a precision or capture-cadence warning contributes to
`restored_notes` and `warning_notes`, not `failed_notes`. Musical-row failures
are reported by the beat stage. Any retained native warning keeps the overall
native status failed until resolved; counting it separately does not suppress it.


Short calibrated cap observations can locate a crossing in an independently
covered displacement phase. Both the measured cap movement and phase movement
must exceed their endpoint uncertainty; every retained position must agree with
one bounded offset. The proof records original PTS, measured displacement,
position errors and offset intersection as `native_motion_support`. Unregistered
origins retain the ordinary fit requirements, and a static cap cannot borrow
motion from neighboring notes.


## Rendered phase and musical gaps

`motion_clock` contains affine parameters and the source window used to estimate
a physical crossing. Its per-note selection and bracket checks live in
`motion_clock_validation`. The parameter reader compares mathematical models
independently of diagnostic fields and JSON key order.

For musical rows, `coordinates/phase_clock.ts` bounds positive constant velocity
from every sample in a complete registered displacement chunk. Its phase budget
includes one observed render step and both declared position endpoint errors;
retained native displacement intervals can enlarge the phase measurement error.
The solver retains all feasible affine models and discards no contradictory
samples. Source gaps, nonmonotone PTS, reverse motion and unsupported nonuniform
chunks supply no such clock.

A source-qualified crossing also retains the extrema of this complete phase
domain, including its cap endpoint uncertainty. A short local fit with a small
RMS residual cannot narrow those bounds: delayed and catch-up captures may bias
its intercept. The physical stage records the source target range in
`motion_clock_validation` before musical rows are considered.

Native endpoint gaps constrain beat-row differences using this velocity domain.
The same domain validates candidate and final musical rows. Original measured
pixel bounds stay attached to their endpoints; clock conversion uncertainty is
recorded separately. Independent coordinate references still enforce their
absolute constraints. The inspector retains the clock domain and source PTS for
review, alongside unresolved motion and timing warnings.


Source-qualified simultaneous-cap checks use the same positive affine-domain
solver for all retained paired positions. Original source frames must cover any
paired visibility gap; only adjacent observed movements supply the render-step
budget. An absent source interval supplies no capture-phase proof. A failed
straight-line point fit cannot discard independent same-frame position bounds.

A certified center keeps its declared reference-scale and sampling-grid error,
even when that exceeds a fixed fraction of the displayed lane spacing. The
intersection of measured gap intervals governs both row-domain constraints and
final concurrency validation. Finer rows retain compatible small separations;
large measurement errors cannot silently become exact simultaneity.

## Slow observed approaches

The clearance between accepted cap measurements and the receptor is spatial.
Slow travel can therefore leave more than 250 ms between the final cap used for
fitting and the receptor crossing. A longer duration does not by itself imply
extrapolation: independent registered peers can measure that displacement through
the crossing. Accept such a crossing only with continuous original playback and
source PTS, nondecreasing shared phase, and independent displacement
support on every intervening captured step in the same registered chunk. Multiple
registered lanes qualify directly. A single lane requires an explicit native
displacement interval and a certified peer identity different from the target;
the target's own trajectory cannot supply that missing independent continuation. Retain
those source timestamps as `motion_clock_validation.supported_approach`.
Missing frames, unsupported steps and uncertified one-lane observations do not
qualify this extension. The same complete proof is required when a cap disappears beyond the
local spatial horizon: distant partial trajectories cannot extrapolate to a target
from their own speed alone. The existing local time limits still bound unsupported extrapolation;
position-error and crossing-uncertainty limits are unchanged.

When the ordinary full-cap clearance leaves fewer than two registered positions
or insufficient measured displacement to distinguish movement from coordinate error,
a certified native center can retain observations whose complete coordinate-error
interval remains below the receptor and above the recorded field boundary. These observations must still pass shared
motion, measured displacement, source timestamp and crossing checks. A stationary
receptor remnant or an unregistered image anchor cannot use this path. Existing
intact approach trajectories continue to use the ordinary clearance band.
