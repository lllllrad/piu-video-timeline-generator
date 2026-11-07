# Independent visual observations

Acquire evidence before chart reconstruction or input association:

```sh
just observe                            # inventory every local metadata window
just observe --acquire --jobs 2          # capture masks, then detect notes
just observe --sources SOURCE --segments 1 3 --acquire
```

The default target is every gameplay window under `.local/data/*/analysis/analysis.json`.
The run plan also lists recordings in `.local/etc` without importing or modifying them.
Unknown layouts remain blocked with a reason. No downloads, metadata OCR, UCS export,
chart policy or report generation is part of this command. The required active banks
cover `arrow-center-xh-review` and `phoenix-arrow-jsg`, including all five directions
and tap/start/body/end reference roles. Other unknown skins do not block mask capture.
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
| `*.masks.bin.gz` | Full-field threshold planes with declared resolution and threshold contract | Accepted heads, body components, timing and successful input |
| `notes/manifest.json`, `notes/*.notes.jsonl.gz` | Localized detector candidates, original frame identity and detector contract | Tracks, target times, popup values, input state and chart metadata |

Timeline and mask capture finishes before skin selection or note detection.
Skin identification and changed detectors decode the unchanged original recording.
Decoded RGB frames are not stored. Compatible independent note observations are
consumed directly without image matching or source decoding. A detector failure
preserves the timeline and spatial masks; unavailable input and popup measurements
remain explicitly `not_measured` rather than claiming a completed channel.

The configured acquisition width is 650 by default. Width, height, crop, layout
and source interval are bound explicitly. Spatial masks are 325 pixels wide and
retain their actual height; use their declared coordinates. Masks cannot recover
pixels discarded by their thresholding. Read the original recording when new
pixel measurements are needed. Source media and timestamps are unchanged.

## Evidence strength

`capture_state: complete` means the requested frame observations were stored.
It does not mean notes were correctly identified, physical inputs measured or
chart reconstruction completed. Mask capture records `recognition_state:
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

Receptor effects require direct shape/animation measurement from the original
source frames. This acquisition does not infer input times from brightness or
an assumed radial growth law. Rendered-effect onset and physical switch time are
different conclusions; any inferred delay needs its own evidence. No placeholder
timestamp or weakly fused estimate is written as a successful input.

## Consumers and integrity

Python `observations.notes.detect_notes` streams original source frames into a detector.
TypeScript `derived/observations/bundle.ts` exposes:

- `manifest(directory)` for provenance and stage state;
- `frames(directory, {channel: 'notes'})` for ungrouped detections;
- `frames(directory, {channel: 'timeline'})` for original frame indices and PTS;
- `spatialMasks(directory)` for packed full-field planes and their geometry.

Each consumed chunk verifies its size and SHA-256. Shared frame indices, source PTS,
playback time, frame counts and source-file identity must agree. Timeline
and mask readers do not load the note-stage metadata or files, so damaged notes
cannot block other channels. Reading an unavailable note stage fails explicitly.

Generic synthetic tests verify that decoded RGB is never stored, chunk boundaries,
nonzero container origins, variable native frame intervals, overlapping candidates,
source invalidation, interrupted publication, detector replacement from original source frames,
detector failure isolation and channel-specific corruption. Native image tests verify
that candidate collection precedes grouping in both serial and parallel workers.
Source-specific recognition cases and skin references belong in the separate data
repository, not this project's tests.


Native hold-image connectivity depends on original image observations, cap
coordinates, measured displacement and the cap-measurement policies it consumes.
Changing a crossing-clock policy, musical subdivision or unused motion diagnostics
does not repeat image connectivity measurement. Source PTS, image content, actual
displacement or cap measurement-policy changes invalidate that evidence. Timed
hold intervals remain a separate consumer and are projected again from the
retained connections and current endpoint timing.


Automatic skin identity counts cap comparisons that satisfy the active reference
regions' declared error bounds. The nonnegative comparison quality ranks these
accepted matches; an additional arbitrary ranking cutoff does not redefine image
acceptance. The independent window, frame, direction and cap-count requirements
still apply, and competing qualified banks remain ambiguous. This identifies a
reference bank without asserting a cap's tap/hold role.

A changed selection policy can consume saved comparisons under unchanged source,
layout, detector and reference bindings. The producer first verifies the previous
decision against its explicit previous requirements, then evaluates the current
requirements and publishes a newly selected decision atomically. It preserves the
original sampling plan, timestamps and pixel hashes. Corrupt decisions fail
explicitly; read-only currency checks never rewrite evidence.
