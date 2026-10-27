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
measured crossing. Remove only the most remote outer sample until a clock
passes, preserving every intervening observation. Every candidate retains the
same sample-count, duration, slope, residual and native-bracket requirements.
Prefer the qualifying window with the lowest residual, down to the existing
0.75-pixel positional floor; among equally precise windows use more native
samples. Retain its bounds, selection method and trimmed-frame count. A distant pause or speed change cannot veto a
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
