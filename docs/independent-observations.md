# Independent visual observations

Acquire evidence before chart reconstruction or input association:

```sh
just observe                            # inventory every local metadata window
just observe --acquire --jobs 2          # capture pixels, then detect notes
just observe --sources SOURCE --segments 1 3 --acquire
```

The default target is every gameplay window under `.local/data/*/analysis/analysis.json`.
The run plan also lists recordings in `.local/etc` without importing or modifying them.
Unknown layouts remain blocked with a reason. No downloads, metadata OCR, UCS export,
chart policy or report generation is part of this command. The required active banks
cover `arrow-center-xh-review` and `phoenix-arrow-jsg`, including all five directions
and tap/start/body/end reference roles. Other unknown skins do not block pixel capture.
Installed references and successful candidate capture do not certify recognition accuracy.

## Ownership and failure boundaries

Data lives at `.local/data/SOURCE/observations/segment-NNN/`, independently of the
existing `play/segment-NNN/` analysis and inspector. Each stage publishes atomically
under a segment lock. Failed work removes its staging files and preserves previously
published evidence. Replaced versions are removed after successful publication.
Capture stops below 32 GiB free space, preserving source recordings and completed data.

| Artifact | Owns | Independent of |
| --- | --- | --- |
| `manifest.json`, `*.frames.jsonl.gz` | Source identity, exact original PTS/playback time, pixel dimensions and shared frame indices | Detectors, tracks, OCR, UCS, input matches, grades and chart exceptions |
| `*.game.rgb.gz` | Complete acquired game RGB, reversibly compressed in bounded 64-frame chunks | Every detector and interpretation |
| `*.input.rgb.gz` | RGB across the receptor row and its surrounding effect area | Note identity, combo updates, judgment words and input associations |
| `*.popup.rgb.gz` | RGB union of declared combo and judgment search areas, before OCR | Counter expectations, recognized grades and note matching |
| `*.masks.bin.gz` | Full-field threshold planes with declared resolution and threshold contract | Accepted heads, body components, timing and successful input |
| `notes/manifest.json`, `notes/*.notes.jsonl.gz` | Localized detector candidates, original frame identity and detector contract | Tracks, target times, popup values, input state and chart metadata |

Pixel capture finishes and publishes **before** skin selection or note detection.
A detector failure cannot discard receptor effects or popup pixels. Skin identification
can sample the published game pixels without reading the original recording again.
A changed detector reads the same pixels and replaces only `notes/`; it never rewrites
the input or popup evidence. Existing skin replay consumes compatible independent
note observations directly, without image matching or source decoding.

The configured acquisition width is 650 by default. RGB compression is lossless
relative to these acquired pixels; resizing/cropping is declared acquisition, not a
claim that this cache preserves the source recording's original resolution. Width,
height, crop, layout and source interval are bound explicitly. Spatial masks are
325 pixels wide and retain their actual height. Their coordinates must not be used
as if they were game-RGB coordinates. The full RGB remains available when masks
have discarded a feature. No source media or source timestamps are changed.

## Evidence strength

`capture_state: complete` means the requested frame observations were stored.
It does not mean notes were correctly identified, physical inputs measured or
chart reconstruction completed. Pixel capture records `recognition_state:
not_evaluated`. The note stage records `candidate_observations`.

The image detector retains every localized candidate **before** proximity grouping,
role resolution, body-subfeature interpretation or track assignment. Each frame-local
candidate index preserves an identity; overlapping positions, competing roles and
sampling variants remain separately inspectable. Failed context comparisons retain
an unknown role and its reason instead of asserting a tap. Candidate counts are not
note counts. Code-based detectors can provide the same contract and `candidates(rgb)`
interface; storage does not require image-template matching.

A channel should directly establish what its visible structure permits. If an overlay,
clipping, capture gap or unsupported rendering prevents that, retain the observation
and concrete failure reason. Another channel may corroborate a conclusion, but its
support must be explicit; uncertain candidates cannot silently become confirmed
observations or remove warnings. Neither brightness nor a failed hold comparison
alone establishes a tap or input.

Receptor pixels preserve expanding note-shaped effect lines for subsequent direct
shape/animation measurement. This acquisition does **not** infer an input time from
brightness or an assumed radial growth law. Rendered-effect onset and physical
switch time are different conclusions; any inferred delay needs its own evidence.
No placeholder timestamp or weakly fused estimate is written as a successful input.

## Consumers and integrity

Python `observations.bundle.game_frames` reads cached RGB with original PTS.
`observations.notes.detect_notes` runs a detector on those frames alone.
TypeScript `derived/observations/bundle.ts` exposes:

- `manifest(directory)` for provenance and stage state;
- `frames(directory, {channel: 'notes'})` for ungrouped detections;
- `frames(directory, {channel: 'input', pixels: true})` for receptor/popup RGB;
- `frames(directory, {channel: 'timeline', gamePixels: true})` for complete game RGB;
- `spatialMasks(directory)` for packed full-field planes and their geometry.

Each consumed chunk verifies its size and SHA-256. Shared frame indices, source PTS,
playback time, frame counts and source-file identity must agree. Input/popup/timeline
and mask readers do not load the note-stage metadata or files, so damaged notes
cannot block other channels. Reading an unavailable note stage fails explicitly.

Generic synthetic tests verify exact RGB round trips across chunk boundaries,
nonzero container origins, variable native frame intervals, overlapping candidates,
source invalidation, interrupted publication, detector replacement without decoding,
detector failure isolation and channel-specific corruption. Native image tests verify
that candidate collection precedes grouping in both serial and parallel workers.
Source-specific recognition cases and skin references belong in the separate data
repository, not this project's tests.
