# Image-based note skins

A skin reference describes a complete image pattern: a tap, a hold's leading
cap with its lower connection, an interior body tile, or a trailing cap with its
upper connection. The cap of a hold is a visual boundary of one held interval.
Neither cap requires an extra tap. A trailing cap's upper body is part of its
image, rather than an optional association inferred from a distant note.

The image detector scans each lane directly. It does not need an outline
candidate, a lane-color threshold, a successful judgment association or an
existing UCS row to propose a location. White-outline detection remains the
default until an image bank is selected for a play. An explicitly selected bank
replaces that detector; missing image matches cannot silently fall back to the
outline model for a different skin.

## References and measurements

Each bank has a skin identity, measured reference lane spacing, and RGBA PNG
templates. The alpha channel identifies supported reference pixels. Each entry
declares its lane kind (0 through 4), role, image anchor and image regions.
Additional same-role templates can cover animation and rendering variants.

Hold-start and hold-end templates must have separate `cap` and `connection`
regions. A start's connection lies below its anchor; an end's lies above it.
Every region must independently pass its masked mean squared RGB error limit.
A large matching cap cannot average away a contradictory small connection.
For a short hold, the opposite cap can overlap a long connection window.
Additional references can compare the nearest visible body rows instead, using
the same independent cap and connection limits. A failed longer window is not
a positive gap; an actual gap must still fail the shorter connection pattern.
The observed start and end bound one held interval, including in these cases.
When caps nearly touch, even the nearest central connector rows can contain
the opposite cap's border. Review the exposed body shoulders beside that cap's
corners instead. A source-derived masked connection region can compare those
shoulders while excluding the opposite cap's center. Validate such references
on other held intervals and on disconnected caps at similar spacing. Cap
proximity alone supplies no connection evidence; thresholds remain unchanged.
The default error limit is 0.015 in RGB values normalized to 0..1; a bank may
require a stricter limit. This is an appearance metric, not a timing allowance.

A confirmed tap additionally requires `clear_above` and `clear_below` image
regions outside the cap. A cap-only reference still locates candidates, but
cannot distinguish a tap from a hold boundary. Missing, hidden or mismatching
context therefore retains the position with `role: unknown` and
`classification_status: cap_only`. Failed connection comparisons on endpoint
images work the same way. Unknown context does not assert a tap or a background
gap. Its reason and all region comparisons remain in the source observation.

Scale references using measured lane spacing. Preserve horizontal and vertical
image transforms separately. The builder resizes the complete source image
before cropping: resizing an odd-origin crop independently changes pixel
sampling. An anchor is an explicit registration convention, not automatically
the center of an arrow-shaped bounding box. Distinctive short, flat or bracket
tails need their own anchor calibration.

Documented HUD rectangles identify areas that can hide a note; they include
transparent space and do not establish pixel occlusion. A positive image match
inside such an area remains evidence under the same per-region RGB limits,
with `hud_region_overlap` retained for review. A mismatching connection cannot
be assumed present behind HUD. It leaves the cap role unknown. Missing patterns
inside a potential occluder remain distinct from clear unexplained losses.
Transparent padding cannot contribute to a comparison. Declared surrounding
source pixels may supply interpolation context; output outside comparison
regions supplies no cap/body coverage or foreground-overlap evidence.
The lower search limit applies to note anchors. Surrounding image context can
extend beyond that limit while remaining inside the original game image; it is
still subject to HUD support checks. A fully visible template must not be
rejected just because its canvas extends below the anchor limit.
Local image minima supply cap positions. Body tiles retain every vertically
qualified origin, using horizontal minima to localize the lane pattern. A better
match on an adjacent row does not erase positively compared body pixels. Nearby
matches from the same role are grouped, retaining their individual comparison
coordinates and errors as alternatives; coverage uses their supported regions.
The body-candidate contract is independent of cap localization, so a body-only
rule change can reuse unchanged native cap observations after reference validation. A complete end pattern has additional connection evidence
that a cap-only candidate lacks; retain the end and both image comparisons.
Contradictory complete tap/hold patterns remain a type conflict, including both
source-frame interpretations. Unknown frames do not erase a positively observed
tail role, while an actual tap or competing start observation prevents automatic
ownership. Competing start/end patterns remain unknown. No input effect establishes an
image role. Unsupported transparency, background overlap, clipping and
unrepresented animation phases can still produce missing or ambiguous matches.

## Source-bound native cap centers

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
center. This registers the same geometric convention as independent native cap
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

Native-scale dimensions must remain unchanged after the detector's declared
spacing transform; rounded lane-coordinate storage cannot silently resample a
reference. A changed image, mask, anchor or source declaration invalidates its
certificate. Runtime validation needs the saved proof and immutable references,
without decoding source video. Metadata-only certification can reuse unchanged
cap/body acquisition groups.

The representative detection keeps its original image identity and coordinate.
A positively matched registered alternative can supply a coordinate proof only
at exactly that same native row. The sample records its actual reference,
comparison index and cap error; failed context does not erase positive cap
pixels. A nearby row cannot transfer calibration. All positively matched
registered coordinate intervals must intersect. Mutually contradictory
comparisons produce an explicit per-track warning and do not supply chord or
independent coordinate-model support; raw detections and comparisons remain.
Pair support counts use only jointly qualified source-frame measurements.

Coordinates retain registration only for the reference that actually supplied
the positive cap measurement. Uncertainty is converted through the actual
vertical reference scale with a one-analysis-pixel raster floor. Cross-template
concurrency uses these centers only within the existing one-pixel coordinate
budget and all ordinary gap, motion, duration and PTS checks. Larger scaled
uncertainty cannot widen that budget; unregistered references retain the
identical-reference constraint. Complete chord proofs list the registered
image references they used. The bank-wide absolute registration warning and
UCS export gate remain in force.

## Data flow

`frames.jsonl` retains each native image observation, including original source
PTS, playback time, role, template identity, skin identity, image bounds,
per-region errors and competing matches. `visual_channels.note_types` joins
those observations to trajectories by exact source frame, lane and detected
position. Derived observations retain their own template, image errors and
source anchor, and reference `frames.jsonl` for the complete competing patterns.
Body diagnostics likewise retain exact frame/lane/anchor references instead of
copying every native alternative. The original comparisons remain unchanged in
the native trace. Conflicting tap/hold observations remain conflicts.

Native image-anchor records also feed independent spacing validation. Each
trajectory point must identify one positive cap comparison at the same source
frame, lane and measured row, under the acquired bank identity. Missing or
inconsistent provenance fails explicitly. These are measured template anchors,
not an inferred outline offset or a claim of absolute game-engine calibration.
Independent coordinate models retain their existing reference-count, lane,
source-support and pixel-residual requirements. Absolute registration remains
unverified for UCS export. Cross-template chord calibration is not supplied by
these records. Concurrent notes can instead establish a visual chord through
one identical cap reference: its shared anchor offset cancels. Reference
identity includes image/mask bytes, cap bounds, scale, lane kind and anchor.
Context-window variants can share this identity while different cap pixels or
geometry cannot. Every point in that witness uses the same fixed cap identity,
original source frame and existing gap/motion/error limits. Different unreviewed
templates or poses cannot be pooled to claim calibrated simultaneity.

A complete end image supplies a tail role without inventing a tap or a press at
that location. It remains a warning when complete hold geometry is unresolved.
Image-based holds require positive start/end identities and connected body
image evidence. Short intervals can have complete coverage in at least four
frames spanning 65 ms and half a lane spacing of motion. A long interval can
instead connect positive image regions through consecutive source frames;
its start and end need not be visible together. This path requires body-tile
support in at least four distinct frames spanning 65 ms, and a measured cap
approach of at least half a lane spacing.

Temporal edges use registered frame displacement, or agreeing observations of
identified caps. Missing motion, failed coordinate registration, a source-frame
gap over 50 ms, competing endpoint identities or a positive tap inside the body
prevent that connection. No fixed scroll speed, interpolated image or input
label supplies body evidence. Regions retain source PTS, measured row bounds
and graph edges. Their bounds describe positive compared rows, not a filled
interval in every frame. Previously positive rows that lose clear support stay
warnings; only documented foreground HUD footprints can explain those losses.

Coverage uses rows with actual compared alpha support in the acquired reference
bank, preserving unsupported internal gaps.
A template canvas rectangle cannot bridge padding or uncompared rows. The bank
identity must match the native observations; changed references fail explicitly.
Deduplicated complete image matches retain their own measured row support;
the representative cap or body tile does not replace other positive comparisons.
Only complete alternatives with the same resolved role can extend that support.
Unknown patterns and opposing roles cannot supply missing connection pixels.
These rows establish image-comparison coverage, rather than a solid foreground
segmentation. Varying endpoint separation, contradictory roles and competing ownership
prevent reconstruction. A missing image match is not a positive observation of
a physical gap. Clear frames without sufficient connection support supply no
proof and remain explicit warnings, even when other frames uniquely establish
the held interval. If the independent positive frames are insufficient, the
whole interval remains unresolved.
Frames with unknown cap context do not erase positive endpoint identities.
Their positively compared cap rows can support the known endpoint location;
failed connection regions supply no coverage. Independent positive body images
must bridge the cap to the interval. Complete role images in other frames must
still establish the start/end identities. Without those roles or sufficient
positive body coverage, the hold remains unresolved. A contradictory complete
role still prevents ownership.
Legacy lane-color components cannot create a hold for a selected image skin.
Body ownership is limited to the established endpoint interval in each source
frame. Another body image elsewhere in the same lane and frame remains
unresolved; a valid hold cannot account for the entire lane.
Receptor observations attach held-state evidence only after geometry exists.
A dim lane-local receptor change can use a nearby positive combo/judgment
update as corroboration inside the certain image-hold interval. Common flashes,
MISS updates and legacy color-body detections cannot supply that support.
It remains sustained recognition, without a new press or release timestamp.

New banks currently remain explicitly uncalibrated for UCS export. An image
location is useful acquisition evidence but does not prove that its anchor
matches the game's timing convention. `skin_registration_unverified` stays
visible and UCS export fails explicitly. The reference collection in ignored
local storage is experimental; it is not a complete validated skin catalogue.
Per-note random skins and downward travel are outside this workflow's current
scope. They require separate skin selection or motion models.

## Receptor-local hold ambiguity

A body image anywhere in the field does not imply hold ticks at the receptors.
Popup-ownership deferral requires connected positive hold-image support starting
within 0.75 lane spacings below the receptor and spanning at least 1.25 spacings,
or a verified endpoint connection intersecting a band extending 0.25 lane spacings on each side
of the receptor. A distant body tile, a short disconnected patch or a failed connection
cannot establish that local ambiguity. All of those image observations remain
in the native trace and geometry diagnostics.

This is a candidate for possible hold-related judgments, not evidence of a
button press or a complete held interval. Its interpretation has a separate
contract component. Updating it reuses unchanged cap/body image acquisition
and recomputes the frame flag without RGB decoding. It does not change the
source timestamps, image comparisons or the actual hold-geometry requirements.

## Commands

Inspect actual reference masks and comparison regions:

```sh
mise exec -- python -m piu_timeline.play.skins review-bank \
  .local/cache/note-skins/example/bank.json --lane-kind 2 \
  --output .local/cache/play-diagnostics/example-reference-regions.html
```

The page shows each template at four times its native size, with its original
alpha mask, exact comparison-region boxes and anchor. A source-frame annotation
box around a detected position does not describe the template's size or support.

Build a bank from reviewed source-image rectangles:

```sh
mise exec -- python -m piu_timeline.play.skins build \
  .local/tools/skin-reference-spec.json --output .local/cache/note-skins/example
```

The specification supplies `skin`, `spacing_pixels`, optional `analysis_width`,
and `templates`. Each template supplies `id`, `lane_kind`, `role`,
`source_image`, `crop` (`left, top, right, bottom`), `anchor_pixels` relative to
that crop, and `regions` containing `name`, `box` and optional `maximum_error`.
Each region can also supply nonempty `comparison_boxes`, a list of integer
`[left, top, right, bottom]` boxes in the same crop coordinates. They must lie
inside that region and select at least eight supported source pixels. Overlaps
are a union. The builder transforms them with the complete source image before
cropping, and the reference viewer draws the selected boxes. Invalid or vanished
support fails explicitly.
Optional `sampling_context` boxes use the same crop-relative coordinates. They
declare actual surrounding source RGB needed by interpolation, without adding
comparison regions or geometry coverage. Include sufficient context around a
cap and its clearance/connection probes; a crop at the cap edge may leave its
resampled boundary unmeasurable. Context outside the source crop is rejected.
Retain `source_evidence` with media identity, source PTS, playback time and game
ROI for recording-derived examples. The builder preserves it in the bank.
Output directories are never overwritten. PNGs, source frames and
recording-specific reference specifications stay outside Git.

Inspect a short source interval without changing its report:

```sh
mise exec -- python -m piu_timeline.play.skins scan SOURCE \
  --segment 1 --bank .local/cache/note-skins/example/bank.json \
  --start 120 --duration 3 --output .local/reports/image-review/observations.json
```

Select a bank for the public analysis path:

```sh
just play SOURCE --segment 1 --note-skin .local/cache/note-skins/example/bank.json
```

For repeated use, `.local/data/SOURCE/note-skins.json` can select a bank:

```json
{"schema":1,"profiles":[{"segments":[1,3],"bank":"../../cache/note-skins/example/bank.json"}]}
```

Bank paths in this file are relative to its source directory; duplicate segment
selections fail explicitly. Bank/image bytes and detector rules participate in
cache identity. A changed bank rescans source RGB without metadata OCR, retaining
counter observations and original PTS. The current threshold-plane cache cannot
reconstruct RGB; image detection changes can therefore reread original media.
Replay treats competing tap/start/end references as one cap group and interior
body references as an independent group. Unchanged groups are reused only when
the acquired bank is still available with its original identity, the detector
rules and spacing agree, and all ordered reference measurements in that group
are identical. Body-only updates scan body images without repeating cap search.
Proven metadata-only reference updates reuse both groups without decoding. An
unverifiable old bank or changed detector rules require fresh acquisition.
Missing native image observations or invalid source timestamps fail explicitly.
The original contour trace is preserved in `frames.outline.jsonl` when switching
an existing play to an image bank. Original media remains unchanged.

RGB frame detection uses separate CPU worker processes, defaulting to half the
available CPU affinity, capped at eight. Set `PIU_SKIN_JOBS=1` for serial execution
or an explicit value up to 32. At most two RGB frames per worker are in flight;
workers share one frozen reference bank and results return in source order.
The parent retains the original image for counter reads and never substitutes
worker completion time for source PTS. Worker failures fail the analysis and
close acquisition. Changing worker count does not change the detector contract.
Programmatic callers that start workers must use a guarded Python main entry
point, as the bundled CLI does.

Image-review JSON includes the detector contract, analysis dimensions and layout
as well as reference identity and original timestamps. An empty decoded timeline
fails explicitly rather than producing a successful report with no observations.

## Rigid hold length from registered endpoints

A connected hold can have different rounded cap coordinates in successive frames.
When a nominal constant-length test fails, `derived/holds/extent.ts` intersects
per-frame length intervals from independent head and tail registration errors.
Only source-bound native image-anchor comparisons provide these errors. At least
four qualified pairs spanning 65 ms must agree; incompatible intervals still fail.
The original compared image regions, connected-body support, unique ownership and
motion requirements remain necessary. Timing or successful input cannot provide
missing image geometry. Accepted holds retain the length interval and original PTS.
Unregistered endpoint frames remain an explicit geometry warning, even if nearby
qualified frames establish the hold. This relative length proof does not establish
absolute receptor timing calibration or enable UCS export for an uncalibrated skin.

## Geometry when beat placement fails

An image-confirmed hold must not disappear solely because an endpoint has no
unique musical row. Geometry preparation can reuse its retained `video_target_range`
when native motion reconstruction succeeded and only beat reconstruction rejected
the note. Missing, nonfinite or failed native timing cannot supply this fallback.
The connected image regions, endpoint roles and ownership checks still run.

Such a hold retains its native endpoint bounds and original beat failure records,
and explicitly marks chart timing unresolved. Projection verifies that the displayed
native head range belongs to the original observation. Reports can show that hold
and its sustained evidence; the original timing warnings remain active. UCS draft
placement rejects it explicitly until musical timing is resolved. Ordinary taps and
native reconstruction failures retain their existing eligibility rules.

## Adjacent-frame motion for image connectivity

The image connector consumes measured adjacent-frame displacement independently of
cap type and endpoint timing. Registered same-block displacement has priority.
When it is unavailable, identities observed in both captured frames may supply
motion, including caps whose tap/hold role or target time remains unresolved.
Duplicate identities contribute nothing. Every common peer must agree within
one analysis pixel; the existing 50 ms capture-gap and displacement bounds still
apply. A failed registered-coordinate block cannot fall back to peers.

`derived/holds/image_motion.ts` computes these steps from saved coordinates in one
batch. Peer-based image edges retain the contributing note IDs and original PTS
pair. The native image connector still requires positively compared body regions,
unique endpoints and sufficient observed travel. A peer motion estimate supplies
no missing image pixels, cap classification, beat placement or input timestamp.
