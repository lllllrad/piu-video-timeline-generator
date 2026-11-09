# Source-bound native cap centers

Reference scaling retains the fractional source-grid origin instead of
independently stretching a cropped image to rounded dimensions. It models area
resampling and the native decoder's bicubic kernel, with B=0 and C=0.6 as described
in the [FFmpeg scaler documentation](https://www.ffmpeg.org/ffmpeg-scaler.html).
Exact small rational scales enumerate their source-grid phases (denominator at
most eight); other scales use a quarter-pixel phase catalogue. Every comparison
still meets its original per-region RGB error limit. Catalogue selection is not
proof of arbitrary skin animation or absolute game timing calibration.

An output pixel contributes only when its center belongs to a comparison region
and every nonzero kernel tap has declared source support. Known adjacent regions
and declared source context may participate in interpolation, but no alpha hole
or unknown padding can be filled. Negative cubic coefficients cannot cancel an
unknown source pixel into apparent support. A region with no supported outputs
remains unavailable; a positive cap can survive with unknown type/context and
`null` region errors instead of invented comparisons.
Observations and alternatives retain `sampling_phase_pixels`, `sampling_kernel`
when non-area, and `reference_scale_y`; anchors use the same transform.
Body/connection coverage, receptor risk and native clearance use the matching
kernel/phase's compared support, rather than another variant's rectangle or rows.

After full source-grid resampling, the detector searches the bounding canvas of
compared output pixels. Unused context extending outside the game image cannot
clip an otherwise visible comparison. This does not restore actually clipped
glyph pixels. `sampling_origin_pixels` retains the canvas origin in the resampled
reference, independently of the source-grid phase. A source point projects to
`bounds_origin + phase + scale * source_point - sampling_origin_pixels`.
Role, clearance and coordinate evidence retain this origin; inconsistent anchor
projections fail explicitly. Cropping the original source before interpolation
would change its sampling and is not equivalent.
Coverage tables use the full resampled reference coordinate space. Each image
comparison supplies its own canvas origin when mapping those rows into the game
image. A retained full-canvas observation has origin zero; it must not inherit
the current search canvas's offset. Body risk and clearance use the same mapping.

A region may restrict its comparison to the union of `comparison_boxes` inside
its outer `box`. This separates a shaped glyph from the surrounding source RGB
needed for interpolation. Boxes use source-pixel coordinates; output centers
select their membership, while the full kernel still needs known source pixels.
Excluded corners and holes provide no cap/body coverage even when their RGB is
known context. A narrow central crop must not stand in for a complete cap when
the missing boundary rows are needed to establish hold connectivity or explain
body-pattern matches inside the glyph. Keep distinct connection comparisons:
matching a tap's lower corner is insufficient proof of a ribbon end without the
continued stem above it.

The bank contract declares this optional comparison geometry only when used.
Its boxes participate in the reference hash and native cap identity. Banks
without the field keep their existing comparison semantics and identities.

A uniform body reference can also match the colored interior of a cap. When
every positively compared pixel of every retained body alternative is contained
in positively compared cap pixels in the same lane/frame, retain that body
measurement with `cap_subfeature` proof. It cannot supply independent body
connectivity or receptor hold risk. Unsupported holes, extensions beyond the
cap or a cap in another lane cannot explain it. Partial-group replay recomputes
this relationship after merging both groups; stale ownership cannot survive a
changed cap. Unexplained body images remain geometry warnings.

A reference can carry `native_anchor_registration` for its vertical native cap
center. An optional `native_center_pixels` point separates this independently
measured center from `anchor_pixels`, the local RGB matching origin. Without
that field the two conventions coincide. The center must lie inside the cap
reference and is bound to the source measurement and reference certificate;
changing it invalidates that certificate. A declared point without a qualified
source certificate supplies no correction. This registers the same geometric convention as independent native cap
measurements. It does not establish the game-engine target anchor, capture
latency or absolute UCS calibration.

Create a new bank with individually verified references:

```sh
mise exec -- python -m piu_timeline.play.skins register-anchors \
  .local/cache/note-skins/example/bank.json \
  --analysis .local/data/SOURCE/play/segment-001/analysis.json \
  --registration .local/data/SOURCE/play/segment-001/head-registration.json \
  --output .local/cache/note-skins/example-registered
```

The source analysis must embed the supplied independent native measurement
artifact under the current measurement contract. Source media identity, ROI,
note lane, original detection, PTS, reference crop and measured center must
agree. A missing frame measurement cannot borrow a neighboring track offset.
The command decodes only bounded reference-frame windows, checks exact RGB at
every supported cap pixel and preserves original timestamps. Each certificate
binds the reference pixels/mask/anchor, source identity, source frame hash and
measurement-artifact hash. Output directories are never overwritten. Other
references stay unregistered with explicit reasons in
`anchor-registration-report.json`; their image patterns remain available.

For the bright blue/red/yellow PIU arrow family, source reference geometry can
also be measured directly:

```sh
mise exec -- python -m piu_timeline.play.skins register-centers \
  .local/cache/note-skins/example/bank.json --profile bright-piu \
  --output .local/cache/note-skins/example-centers
```

This opt-in profile measures complete isolated bright cap envelopes inside
supported reference pixels. Truncated, clipped, competing or height-inconsistent
caps do not establish a center. Attached starts use complete cap RGB matches
or the leading boundary and dimensions measured from at least two independently
sourced isolated caps. The dimension model requires matching full width and a
visible lower glyph protrusion outside the stem; the body cannot define the cap
height. Conflicting dimension/RGB estimates cannot supply a center. All supporting
reference sources must independently pass original RGB/PTS verification.
Hold ends use a complete tap-cap RGB correspondence when available. A different
terminal texture can instead match the entire lower half of the filled cap
silhouette, including its outside edges, against at least two independently
sourced complete taps. Both silhouettes must lie within one source pixel of each
other throughout their supported comparison regions. Matching cap heights may
differ by at most one source pixel. The observed lower edge and those independent
heights define the center; a stem edge alone supplies no height. Clipped,
unsupported, competing or inconsistent lower shapes remain unregistered. Both
full-RGB and silhouette estimates must agree when both are available. Saved
measurements identify every source reference and the compared lower regions.
The command independently
checks the original source RGB, ROI, dimensions, PTS and unchanged media identity
before issuing certificates. It saves measurement and verification artifacts,
leaves unresolved references unregistered, and never uses beat rows, targets or
input events. Other skin families require their own measured geometry model.
This registers a visual cap convention, not an absolute game-engine target.

Native-scale dimensions must remain unchanged after the detector's declared
spacing transform; rounded lane-coordinate storage cannot silently resample a
reference. A changed image, mask, anchor or source declaration invalidates its
certificate. Runtime validation needs the saved proof and immutable references,
without decoding source video. Metadata-only certification can reuse unchanged
cap/body acquisition groups.

The representative detection keeps its original image identity and coordinate.
A positively matched registered alternative supplies its own certified center
offset and actual vertical scale. When its matching origin differs from the
representative detection, both compared cap supports must overlap by at least
80% of each support's pixels on the actual target grid. Bounding-box proximity
does not establish this identity. The actual shared-pixel count and both support
fractions are retained as `native_cap_shared_pixel_evidence`.
The sample retains both `detected_y_pixels` and `native_y_pixels`, its actual reference,
comparison index and cap error; failed context does not erase positive cap
pixels. Another glyph cannot transfer calibration. Native acquisition also retains `cap_localization`: a double-precision RGB
residual over the visible, source-supported cap core, its pixel count, and an
independent vertical-contrast residual. Contrast pairs use adjacent observed
rows whose reference RGB difference exceeds that cap's photometric error bound.
Missing vertical features, hidden pairs or a failed contrast comparison cannot
establish a vertical center. A body stripe without a visible boundary is a
refusal case. Missing pixel observations require acquisition; aggregate saved
RGB errors cannot reconstruct this channel.

Occlusion recovery must also remeasure existing weak caps. Its discovery pass
skips neighborhoods that already have a cap, so it cannot correct an initial
shifted match there. Position refinement excludes that cap itself from the
foreground, retains only independently measured neighboring caps, and searches
its original neighborhood using the actual visible two-dimensional footprint.
The initial center is a search seed, not a fixed coordinate. Refinement adds
competing pixel measurements without erasing the original evidence.

RGB acceptance and spatial localization are separate decisions. A positive cap
comparison proposes a position; it does not establish that every positive pose
or sampling variant locates the same center. `derived/skins/localization.ts`
projects the source-bound center convention for each same-cap comparison, then
selects the unique minimum normalized cap RGB error. Reference aliases and
sampling variants at the same center do not compete as different positions.
Distinct centers with scores indistinguishable at the declared numerical
precision remain `image_position_ambiguous`. This precision is a floating-point
score tolerance, not a positional allowance. No best-position choice is made
from motion, input timing, a beat row or a neighboring lane.

The saved `native_cap_localization` records the selected score, the strongest
competing position's score, their separation and the number of distinct positions.
A weaker positive comparison does not widen a point, constrain its location or
turn into independent corroboration. The coordinate is on the sampled image
grid in the certified reference convention; its spatial radius is zero. The
source certificate's fixed geometry budget and a hypothetical half-target-pixel
rounding error are not automatically added to that raster coordinate. This does
not claim a continuous engine position, subpixel accuracy outside the sampled
reference models, or exact target time. Capture phase, motion reconstruction and
reference-convention validity remain separate obligations.

Python validates native comparison pixels, sampling origins and shared cap
support. It sends all per-frame comparison evidence in one batch to TypeScript,
which owns reference-center projection, score competition and the selected
coordinate. A same-reference tracking anchor likewise receives no candidate-
spread radius; indistinguishable different locations cannot provide that anchor.
Pair support counts use only jointly qualified source-frame measurements.

Timing fits use each qualified frame's projected center and retain the raw
trajectory as `detected_points`. A partially registered trajectory uses only frames
with measured center hypotheses for its coordinate fit. Its complete original
detection trajectory stays in `detected_points`; unmeasured image origins never
enter that fit. `image_center_registration_incomplete` identifies every frame
still lacking a center. Missing frames are not interpolated, and ordinary timing
and capture-gap checks must still pass with the measured subset. Mixing raw
origins and corrected centers would create artificial motion.
Conflicting localization hypotheses retain an explicit warning and the original
comparison evidence, without a representative center projection. They cannot
enter a timing fit, certify the trajectory convention or provide a fallback
tracking anchor with an enlarged error. There is no lane-wide or neighboring-
frame center correction. Reapplying registration starts from the raw trajectory.
Image ownership, role joins and hold connectivity use raw matching positions
and original PTS.

A trajectory whose fitted samples all have certified native center bounds can
measure displacement even while it is the only visible note. The native adapter
passes that coordinate basis and error explicitly to shared motion. Such samples
are labeled `measured_cap_displacement`; an unregistered image origin or a
conflicting projection cannot establish this solo support. Joint registration
also accepts a single qualified trajectory and bounds monotonic correction by
its endpoint errors. Unknown frames are not filled, and source PTS, capture gaps,
target-clock checks and independent chord requirements remain separate.

Coordinates retain registration only for the reference that actually supplied
the localized cap measurement. Cross-template concurrency uses these centers
within its ordinary gap, motion, duration and PTS checks. An unregistered
reference retains the identical-reference constraint. Complete chord proofs list
the registered image references they used. Bank review status does not block
automatic UCS drafts; missing or ambiguous coordinate evidence remains explicit.

Cross-template image chord checks intersect the signed inter-head gap bounds
from every qualified co-observed frame. Each bound uses both certified endpoint
uncertainties in analysis coordinates. The common interval must intersect the
existing lane-spacing-relative chord gap limit. A passing median cannot hide a
contradictory frame. The proof retains the gap interval, individual endpoint
errors and source PTS; unsupported or conflicting positions remain warnings.
Legacy positions without these source-certified per-frame bounds retain the
strict point-gap check. All duration, displacement, motion, domain uniqueness
and reference requirements still apply.

Beat-spacing validation also checks coordinate conventions between trajectories.
An unregistered matching origin cannot be subtracted from a certified cap center,
even when both trajectories have smooth motion. Such a pair records an explicit
`incompatible_coordinate_origins` failure on the unsupported track; it cannot
reject a source-certified neighbor. Unregistered image tracks cannot supply
independent affine reference coordinates or recovery anchors. Relative checks
between unregistered tracks require the same unchanged image reference throughout
both trajectories, so the matching-origin offset cancels. Certified coordinate
contradictions still fail the ordinary spacing checks. These checks use native
positions and source PTS, independently of input and judgment timestamps.


## Localization validation

`tests/derived/skins/raster-localization.test.ts` renders taps and both boundaries
of holds from the synthetic scene generator. It checks all expected centers
against independently supplied scene positions across three animation poses,
movement and four image scales. `localization.test.ts` separately checks weaker
shifted matches, equal-score ambiguity, reference-anchor conversion, alias
invariance, unchanged transport and rejection of added spatial budgets. These
checks do not certify untested skin artwork or a corpus recognition rate.
