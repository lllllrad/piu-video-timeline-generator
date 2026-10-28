# Shared motion and crossing clocks

A shared displacement relates identified moving notes through
`y_i(t) + d(t) = c_i`. Original positions, recording times and source PTS remain
unchanged. The target solves `y_i(T) = receptor_y`; no input observation or UCS
row supplies the motion. Absolute registration and capture latency remain
separate uncertainties. See the [visual model](gameplay-visual-model.md).

Acquisition requires three one-to-one head correspondences across two lanes.
Final registered identities require two corroborating heads in different lanes
or separated vertically by more than 0.65 lane spacings. A corroborated identity
can carry measured displacement for at most 250 ms after losing peers. Missing
observations and ambiguous correspondence break the coordinate block. Joint
registration retains raw positions and exposes inconsistent measurements.

A corroborated head moves one screen pixel per shared displacement pixel.
Inconsistent measured slopes are refused. Intact observations below the HUD
supply occlusion predictions; partial bounding-box centers cannot override them.
Target estimates are continuous, without rounding to frames or beat quotas.

A constant-speed clock needs at least 16 native samples spanning 300 ms. Its
positive velocity, residual and agreement between the two half-window slopes
must pass the existing checks. The residual limit is the greater of 0.75 pixels
and half a capture interval of motion plus 0.75 pixels. The half-window slope
limit is 8% plus the measured residual-derived uncertainty.

The complete block clock is checked against the actual before/after crossing
frames. If it fails, a local clock starts within 500 ms on either side of the
measured crossing. Test contiguous windows containing both actual crossing
frames, including windows with the crossing near either end. Each window
retains every intervening observation and rejects source gaps over 50 ms.
Every candidate retains the same sample-count, duration, slope, residual and
native-bracket requirements. The predicted phase at both bracket frames must
also fit the existing capture-interval and position-error allowance. A phase
jump inside the bracket cannot become an averaged-away outlier in a longer
flank. A later pause can therefore leave a separately supported earlier
crossing intact, without supplying a clock for the pause itself.
Prefer the qualifying window with the lowest residual, down to the existing
0.75-pixel positional floor; among equally precise windows use more native
samples. Prefer the nearer center only when precision and support are tied.
Retain its bounds, selection method, trimmed-frame count and bracket-phase
errors. A distant pause or speed change cannot veto a
separately supported neighborhood. A discontinuous or poorly supported crossing
remains an explicit reconstruction failure. No failed clock silently becomes a
local per-note estimate or interpolated timing in registered reconstruction.

Capture cadence, displacement error and clock residual remain in the target
range. Heads last observed in the HUD retain their bounded shared-motion
proximity policy; other heads keep the ordinary proximity bound. Transfer
between coordinate blocks and short extrapolation have separate observation,
identity, source-continuity and distance checks. No song-wide speed fills gaps.

`scroll_motion` retains displacement and supporting identities. Per-note
`fit_method`, `motion_target_phase`, clock model and crossing-frame PTS explain
the result. Native detections can be refitted without RGB acquisition or OCR.
Selecting a clock never removes the independent visibility or motion warnings.

[Independent native spacing](beat-row-domains.md#targets-without-a-successful-crossing-clock)
can separately establish a chart target when a crossing clock fails. That method
does not restore or substitute a source motion clock.

Independent reference models predict gaps in registered native coordinates.
Compare those predictions with the tested heads' fitted offsets in the same
coordinate block. Each head must already pass the native observation-residual
checks, and the tested pair remains excluded from the independent references.
The comparison keeps the existing pixel limit. An adjacency-only subset of
rasterized positions can have a biased median even when the full native fit
is valid; retain that median separately as `observed_gap_pixels`, alongside the
actual `comparison_gap_pixels` and its coordinate basis. Every independently
supported model must agree, including when different blocks support the pair.

A rejected clock or shared-clock spacing conversion can leave valid native
positions. Both failures may enter independent beat-coordinate recovery, with
the rejected time used only to locate a reference window. The failed note
cannot serve as a reference. Native outliers, missing independent references
and ambiguous rows still prevent recovery. Only a successfully recovered and
revalidated note retires its original timing-failure warning; other motion or
visibility warnings remain.


## Converting beat corrections to pixel gaps

Native relative positions keep their existing pixel tolerance. When no independent
native coordinate model is available, a shared clock converts a beat-corrected
time difference into a distance. Its velocity is a measurement with uncertainty.
Use three clock residuals divided by the source-window duration as the velocity
error, consistent with the residual-over-window rule for short extrapolation.
Multiplying that error by the tested target-time gap gives a separate conversion
uncertainty; retain it alongside the native pixel tolerance in the diagnostics.

This applies only to corrected targets using the same measured clock. Unchanged
native targets, exact clocks and independent native-reference models retain the
original image gate. A wrong row outside the combined bound still fails. No
additional beat candidate, input association or missing image is created by this
conversion check.

## Observed reverse movement

The ordinary approach moves upward (decreasing image y). A clearly downward
native trajectory must remain a motion warning even if its speed is constant
or it already has a target/input association. Use the same four-observation
windows and capture-gap checks as speed-change measurement, outside known HUD
occlusion and receptor/bottom exclusion areas. Require the lower signed-velocity
bound, including fitted residual and two pixels of endpoint uncertainty, to be
strictly positive. Merge consecutive supported windows and retain their source
PTS, direction, count and velocity bounds as `reverse_scroll_motion`.
Stationary raster jitter, an unsupported slope or a capture gap does not prove
reverse movement. This observation alone does not establish a playable reverse
scroll gimmick, decorative art, a press or a successful judgment. Those require
their own source evidence and concrete chart handling.


## Repeated captured positions

A series of source frames can retain exactly the same registered displacement
before the next distinct phase. It can represent a real scroll pause or repeated
capture of an older rendered image; frame timestamps alone cannot distinguish them.
When the target lies beyond that stationary phase, the crossing bracket starts at
the first contiguous stationary sample, rather than its final duplicate. The clock
may supply an estimate inside that bracket, but its uncertainty must cover the
whole unresolved capture interval. `stationary_phase_interval` retains the original
recording/source-PTS endpoints and explicitly records both interpretations.

This does not synthesize images or timestamps, discard repeated frames, change
pixel-error limits, or exempt stop/motion warnings. Missing or invalid source gaps
cannot be bridged by the plateau search. Ordinary non-repeated captures retain
their existing precision. Synthetic stored-observation scenes vary capture rate,
scale, repeated images and dropped frames independently of chart-event truth.
