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
caps do not establish a center. Attached starts require complete cap RGB matches
to those isolated references, with intersecting center bounds across all qualified
comparisons. Hold ends have no automatic center model. The command independently
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
A positively matched registered alternative can supply a coordinate proof only
whose matching anchor coincides with the original detection. Project that
comparison with its own certified center offset and actual vertical scale.
The sample retains both `detected_y_pixels` and `native_y_pixels`, its actual reference,
comparison index and cap error; failed context does not erase positive cap
pixels. A nearby row cannot transfer calibration. All positively matched
registered coordinate intervals must intersect. Mutually contradictory
comparisons produce an explicit per-track warning and do not supply chord or
independent coordinate-model support; raw detections and comparisons remain.
Pair support counts use only jointly qualified source-frame measurements.

Timing fits use each qualified frame's projected center and retain the raw
trajectory as `detected_points`. Frames without a proof keep their original
detection; there is no lane-wide or neighboring-frame center correction.
Reapplying registration starts from the raw trajectory. Image ownership, role
joins and hold connectivity use raw matching positions and original PTS.

Coordinates retain registration only for the reference that actually supplied
the positive cap measurement. Uncertainty is converted through the actual
vertical reference scale. The one-pixel bound belongs to the original
reference image, including its native raster measurement; a half-size analysis
therefore carries a half-analysis-pixel bound. Resampling retains the declared
source-grid phase and does not introduce a second analysis-pixel floor.
Cross-template concurrency uses these centers only within the existing
lane-spacing-relative coordinate budget and all ordinary gap, motion, duration and PTS checks. Larger scaled
uncertainty cannot widen that budget; unregistered references retain the
identical-reference constraint. Complete chord proofs list the registered
image references they used. The bank-wide absolute registration warning and
UCS export gate remain in force.

Cross-template image chord checks intersect the signed inter-head gap bounds
from every qualified co-observed frame. Each bound uses both certified endpoint
uncertainties in analysis coordinates. The common interval must intersect the
existing lane-spacing-relative chord gap limit. A passing median cannot hide a
contradictory frame. The proof retains the gap interval, individual endpoint
errors and source PTS; unsupported or conflicting positions remain warnings.
Legacy positions without these source-certified per-frame bounds retain the
strict point-gap check. All duration, displacement, motion, domain uniqueness
and reference requirements still apply.
