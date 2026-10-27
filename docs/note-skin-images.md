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

The detector rejects compared support pixels intersecting documented HUD
rectangles. Transparent padding and pixels outside the declared comparison
regions do not make an otherwise clear cap or connection hidden. Every supported
pixel still has to be outside HUD; both cap and connection checks remain mandatory.
Local image minima supply candidate positions. Nearby matches from the same
role are deduplicated. A complete end pattern has additional connection evidence
that a cap-only candidate lacks; retain the end and both image comparisons.
Contradictory complete tap/hold patterns remain a type conflict, including both
source-frame interpretations. Unknown frames do not erase a positively observed
tail role, while an actual tap or competing start observation prevents automatic
ownership. Competing start/end patterns remain unknown. No input effect establishes an
image role. Unsupported transparency, background overlap, clipping and
unrepresented animation phases can still produce missing or ambiguous matches.

## Data flow

`frames.jsonl` retains each native image observation, including original source
PTS, playback time, role, template identity, skin identity, image bounds,
per-region errors and competing matches. `visual_channels.note_types` joins
those observations to trajectories by exact source frame, lane and detected
position. Conflicting tap/hold observations remain conflicts.

A complete end image supplies a tail role without inventing a tap or a press at
that location. It remains a warning when complete hold geometry is unresolved.
For image-based holds, start/end identities and directly matched body tiles must
cover the intervening image interval in at least four frames spanning 65 ms and
half a lane spacing of motion. Varying endpoint separation, contradictory roles and competing ownership
prevent reconstruction. A missing image match is not a positive observation of
a physical gap. Clear frames without sufficient connection support supply no
proof and remain explicit warnings, even when other frames uniquely establish
the held interval. If the independent positive frames are insufficient, the
whole interval remains unresolved.
Frames with unknown cap context do not erase positive endpoint identities.
They supply no endpoint coverage proof; the remaining complete images must
independently satisfy the same geometry requirements. A contradictory complete
role still prevents ownership.
Legacy lane-color components cannot create a hold for a selected image skin.
Receptor observations attach held-state evidence only after geometry exists.

New banks currently remain explicitly uncalibrated for UCS export. An image
location is useful acquisition evidence but does not prove that its anchor
matches the game's timing convention. `skin_registration_unverified` stays
visible and UCS export fails explicitly. The reference collection in ignored
local storage is experimental; it is not a complete validated skin catalogue.
Per-note random skins and downward travel are outside this workflow's current
scope. They require separate skin selection or motion models.

## Commands

Build a bank from reviewed source-image rectangles:

```sh
sh scripts/run.sh .venv/bin/python -m piu_timeline.play.skins build \
  .local/tools/skin-reference-spec.json --output .local/cache/note-skins/example
```

The specification supplies `skin`, `spacing_pixels`, optional `analysis_width`,
and `templates`. Each template supplies `id`, `lane_kind`, `role`,
`source_image`, `crop` (`left, top, right, bottom`), `anchor_pixels` relative to
that crop, and `regions` containing `name`, `box` and optional `maximum_error`.
Retain `source_evidence` with media identity, source PTS, playback time and game
ROI for recording-derived examples. The builder preserves it in the bank.
Output directories are never overwritten. PNGs, source frames and
recording-specific reference specifications stay outside Git.

Inspect a short source interval without changing its report:

```sh
sh scripts/run.sh .venv/bin/python -m piu_timeline.play.skins scan SOURCE \
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
