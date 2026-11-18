# Native image results and tracking inputs

The image stage compares templates, sampling phases and local positions internally.
Those comparisons are measurements used to resolve an image, not additional notes.
A completed stage publishes coordinates and explicit role/classification results.
A contradictory role or unregistered center stays unresolved; it is not converted
into a confident note to make the output smaller.

Previously each normal frame serialized every image comparison under
`skin_observations[].alternatives`, then duplicated caps under `notes`. The tracking
stage parsed these searches and repeated native coordinate resolution. A sampled
frame from `4MyMJse0L0g` contained 1,388 comparisons for one note and occupied
14,520,268 bytes. This is a stage-contract problem, not a necessary cost of tracking
four image observations.

## Published contract

`frame_result_format` identifies the current output contract. Normal frames contain:

- `notes`: lane, position and resolved coordinate results bound to the source bank.
- `skin_observations`: selected image metadata and explicit role/conflict proofs.
- Original source PTS, playback time, counter observations and risk flag.
- A hash-bound reference to compressed native comparison evidence.

There are no full comparison search lists in these normal frame results. Image
coordinate resolution runs before publishing. Tracking reuses `position_result`
without running localization again; it rejects a result from another bank. Later
trajectory grouping does not change the underlying image position measurement.

`comparison-evidence/<SHA256>.json.gz` retains the original image measurements once,
without duplicating them in `notes`. This separate input supports source inspection
and native operations that genuinely require original pixel-comparison coverage,
such as hold connectivity, clearance and risk remeasurement. These native producers
request `stream_frames(..., comparisons=True)` explicitly. The default reader,
tracking and ordinary channel projection use small results. Evidence reads verify
the content hash, source PTS/playback binding and local path. The original recordings
are never changed. Existing legacy frames remain readable.

The selected detector contract includes the frame-result format, so a compatible
play refresh republishes the new format rather than silently treating old bulky
frames as current. Existing saved directories are not rewritten in place by a code
update; a normal analysis refresh publishes a replacement through the existing
segment transaction.

## Verification

For the sampled production frame, the published result is 13,917 bytes and the
separate compressed measurements occupy 292,789 bytes. Native coordinates are
identical and restoring the comparison evidence exactly reproduces the original
image observations. These are one-frame measurements, not a whole-dataset storage
estimate or a promise that complete trajectory analysis takes less than a second.
