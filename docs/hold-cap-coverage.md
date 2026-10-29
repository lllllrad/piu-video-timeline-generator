# Native appearance support for a known hold cap

A complete hold's leading and trailing cap remain observable image objects.
Their disappearance does not imply a separate press or physical release. The
processing channel keeps their native samples under `hold_component`, with the
observed cap transition in `cap_observation`. Sustained recognition remains a
separate measurement.

The cap detector's receptor boundary can stop reporting a complete glyph while
part of the cap remains visible below that boundary. A second appearance
measurement uses the same head's own moving native color silhouettes. Each
reference pose requires at least three distinct source frames and half a lane
spacing of observed travel. A positive comparison uses the existing 0.65 color
similarity and white-fraction limit, a complete comparison window and an actual
observed pose. A composite median shape alone supplies no cap-coverage proof.
Unknown, clipped and white-effect samples do not supply coverage.

`cap_coverage` records the compared support rows, full comparison footprint,
score, pose identity, reference frames and original playback/source PTS. It
measures a known cap; it cannot create a new note, body, endpoint, press or
release. The source masks and original recordings remain unchanged.

## Applying the measurement

The derived hold view may corroborate a missing region only for the same
established hold image connection and one of its recorded cap identities.
The source frame and reference frames must match the retained native timeline
and that head's approach observations. The reference must retain moving
support, and its footprint must fit the native cap radius. A large body region
cannot be supplied by a cap-sized comparison.

Subtract only the actual compared row intervals from each reported missing
interval. Uncovered portions retain their geometry warning. A fully covered
loss moves to `accounted_cap_coverage`, preserving the original native warning
and all contributing measurements. Native hold geometry and its source
warning remain in the acquisition-derived artifact; report accounting does
not rewrite that evidence or change chart/input timing.

Internal mask coordinates use the retained processing image's dimensions.
Convert vertical bounds with the actual analysis-height/native-height ratio;
it can differ from the horizontal resize ratio after integer height rounding.
Cap radius and reference travel use measured lane spacing, rather than a fixed
game-screen pixel size.

The processing producer and derived consumer have independent cache inputs.
Rebuilding these measurements reads retained masks, without video decoding or
OCR. Regression coverage includes generated native pixels, consumer projection,
source identity, missing-body controls and held-state input semantics.
