# Native visual registration

## Registering nested outlines consistently

The inner white contour and the outer colored silhouette can have different centers, depending on
arrow direction and skin. Neither a beat-grid match nor a successful input establishes their offset.
For a complete isolated cap, measure the connected outer silhouette around the same white contour in
the retained native neighborhood, including its colored rim. Require visible separation on both
sides and exclude clipped patches and known HUD regions.

Visibility for registration uses the measured outer box in original game-image pixels, rather than a
center expanded by an assumed cap radius. For an isolated cap, also include the same 0.15-spacing
vertical background margins used to prove its separation. All support must lie inside the scrolling
field and below the receptor's 0.3-spacing effect band, and must not intersect a named HUD
rectangle. A center outside a HUD rectangle does not prove that its cap edge is clear. Conversely, a
broader search rectangle overlapping the HUD cannot invalidate a complete cap and its clear margins
outside that rectangle. A connected-cap template needs its full matched box visible, without the
separation margins that would deliberately reject a connected body. Retain each support rectangle
alongside its source PTS. These checks do not change repeated-frame, duration, offset stability or
independent-template requirements.

An observed identity can supply a constant outline-to-silhouette registration offset when at least
eight qualified source frames span 120 ms. Current policy requires 95% of offsets within one native
analysis pixel of their median and a median absolute error at most half a pixel. Limit correction
magnitude to one tenth of lane spacing. These are registration gates, not permission to move a head
to a beat or change the one-pixel inter-note spacing check. An unstable calibration and every
measured outlier remain explicit warnings. A calibrated track contributes at least one pixel of
position uncertainty to its crossing.

Keep all original detection coordinates, frame times and PTS. Each qualified frame uses its own
measured cap center, not the median offset. Unmeasured frames use the constant offset only when
stable; otherwise retain their raw position. Keep these frame counts and fallback basis explicit.
Global offset instability still warns; it does not invalidate independently measured centers. This
neither drops observations nor supplies missing positions or times. Visibility gaps and
appearance/type joins continue using original detections. Connected hold caps, obscured outlines and
unsupported shapes do not inherit a calibration just because other notes in that lane have one. The
calibration measures a rendering coordinate convention; it cannot establish note type, judgment,
press or release.

A stored neighborhood's center is an integer pixel row, rounded during cropping. The original
contour center can lie on a half-pixel row. Convert the measured patch offset back into the original
image coordinate system by adding `round(detected_y) - detected_y`; adding a patch-local offset
directly to the fractional detection introduces an artificial alternating half-pixel error. Keep
this patch-origin correction in the measurement record. It does not move the original observation,
relax a fit gate or change source timestamps.

### Registering a cap attached to a body

A continuous colored body makes a cap's full connected-component bounding box
unsuitable as its registration box. It does not move the glyph's registration
point. A compatible skin can instead supply a local white-outline template from
complete, separated caps in the same lane of the same recording segment.

Templates must be supported by at least two independent observed head identities. Cluster only
equal-size outer boxes whose aligned white-pixel Dice similarity is at least 0.94; keep the original
reference pixels and supporting source PTS. The chosen template image and at least two supporting
identities must be external to the cap being measured; its membership in a larger bank does not
erase valid external evidence. Do not iterate on inferred templates. Already calibrated heads also
retain qualified template measurements for additional source frames. A body outside the cap box may
differ; white pixels inside it must still match. A cap with a genuinely different design or an
obscured outline remains unsupported.

Search bounded native translations, require Dice similarity at least 0.90, and reject a competing
registration more than 0.75 pixels away unless its similarity is at least 0.04 lower. Clip/padding
validity and lane-color support still apply. Inferring an offset for unmeasured frames still
requires the same repeated-frame stability gates. Actual native measurements keep their own centers
even when no constant fallback is supported. Before fitting, independently learned complete-cap
templates can also check an isolated outline's measured box. Compression or nearby artwork can leave
a plausible but truncated white contour whose box does not enclose the full glyph. The existing
unique template-matching gates must prove a complete cap box containing the measured box and at
least three pixels taller; a merely shifted or differently sized alternative is insufficient. Use
that complete cap's coordinate and preserve the original outline measurement in
`outline_observation`. The full matched cap must stay outside HUD, clipping and receptor effects; an
independent template does not need isolated background margins. Keep every source frame in the fit.
Missing or ambiguous template proof never removes a contradiction, and remaining offset instability
still warns. Templates provide coordinates only: matching a glyph does not classify a tap or hold,
establish body ownership or prove input.

A neighboring-head spacing check selects a pair when the heads are adjacent in
height. Its common coordinate proof may use every frame where those same two
identities are observed together inside the selected source-time interval, even
if a third head lies between them in some frames. Height adjacency does not erase
simultaneous coordinate evidence. Retain the minimum four registered observations
spanning 65 ms, the observed gap/scatter and the existing pixel tolerance. Do not
borrow support outside the checked interval or from a block lacking either head.
Sort source times independently of trajectory storage order before defining that
interval; processing a short track first must not change the geometry verdict.

The common song phase must explain native inter-head distances as well as timed
beat rows. Evaluate each bounded audio-phase candidate with the same registered
spacing check used for the final output. Prefer the candidate with the most
jointly consistent observed heads, then supported timing targets and simpler
subdivisions. This uses measured geometry, never grades, input associations or
an authoritative note count. A candidate that fits many time intervals while
moving neighboring notes away from their observed separation is not supported.

Record candidate scores and accepted identities. Equal best candidates with
different row configurations or supported identities remain an explicit phase
failure. The representative phase must reproduce the winning support set; do not
average across incompatible spatial solutions. Retain the existing audio bounds,
phase-search resolution, source timing uncertainty and pixel gates.
