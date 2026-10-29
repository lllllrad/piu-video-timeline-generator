# Coordinate frames and stage inputs

Coordinates have both a screen frame and an anchor convention. Sharing pixel
units does not make two anchor conventions comparable. Qualification belongs to
the measurement producer; a smooth trajectory, beat row or input match cannot
establish it.

## Screen and time frames

| Quantity | Units and origin | Conversion owner |
| --- | --- | --- |
| Layout lanes, receptor and native detection `x`/`y` | Fraction of the analyzed game crop; top left, y downward | Native screen/detector adapters multiply by analysis width/height |
| Original track positions | Analysis-image pixels; game-crop top left, y downward; recording seconds | Detection adapters retain the matching/outline anchor |
| Projected cap centers | The same analysis-image pixel frame; independently measured cap-center anchor | `play/head_registration.py` and `derived/skins/centers.ts` apply registered projections |
| Reference image anchors and center uncertainty | Original reference-image pixels | `play/skins/coordinates.py` uses the actual vertical reference scale and sampling origin |
| Scroll phase and fitted head offset | Analysis pixels in a motion chunk; `head_offset = image_y + phase` | `derived/registration.ts`; offsets from different chunks have no common origin |
| Native frame PTS | Original media stream time | Acquisition retains it beside recording time; consumers check the saved timeline |
| Note targets and input brackets | Original recording seconds | Separate motion/beat and visual-input consumers; an input bracket cannot move a chart target |
| UCS timing | Song-relative beats/rows and seconds | Verified audio translation and official UCS tempo sections; no media retiming |

Analysis resolution is not fixed. Pixel quantities must be interpreted with the
saved dimensions and lane spacing. A reference-pixel uncertainty scales once
into analysis pixels; there is no second analysis-pixel floor in registration.
Geometric cap centers do not establish engine timing anchors or capture latency.

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
| `native_cap_center` | Source registration, scaled error and current position agree | Bounded center distances and independent references, subject to each consumer's ordinary limits |
| `image_reference_anchor` | Original image-matching origin | Relative distances only when both origins use the identical reference |
| `conflicting_center_projection` | A projected center convention with conflicting localization hypotheses and a retained encompassing error | Preserve the trajectory convention and warning; do not supply an independent frame measurement |
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
