# Local storage and analysis history

Original recordings live under `.local/data/SOURCE/raw/`. Current play results
under `play/segment-NNN/` retain original source PTS, registered coordinates,
hold and role measurements, counter crops, and pixel feature caches. Image
banks are versioned in the separate data repository. Promotion updates complete
JSON path values atomically without reserializing numerical observations. Files
with no affected paths retain their exact bytes and modification times.

The pending play build uses `frames.jsonl` for native observations. Image
comparisons are stored in compressed, content-addressed files. After all frame
consumers and report rendering succeed, the build removes `frames.jsonl` and the temporary `comparison-evidence/` files.
The registered coordinates, support and conflict results remain available.
`frames.combo-baseline.jsonl` holds the original counter fields and source
timestamps. Legacy snapshots with `frames.base.jsonl` remain readable.
A rebuild that requires retired frame observations reacquires them from the
original recording. Saved file stages and report rendering use their own
published inputs.

## Automatic retention

Successful metadata and play publication keeps the current directory and removes
all superseded `analysis.previous-*` and `segment-NNN.previous-*` snapshots, along
with abandoned builds for that canonical result. Successful metadata cache reuse
and cached play refreshes also apply retention. Unrelated segments, original
media and human-named directories are outside its scope. Symlink directories
are never followed for deletion.

Failed analysis does not trigger retention. A play keeps its history unless its baseline and report are present together
with either a native trace or a completed frame retirement and saved coordinates. Original recording paths,
including symlink targets, protect containing directories from removal.

Publication remains protected by the source/segment writer lock. A shared
`.retention.lock` additionally pins snapshot selection and staging while another
segment reuses a saved observation snapshot. Pruning takes the exclusive side of
that lock, after staging has completed. Long-running inference does not hold the
history lock. Retention is implemented in `derived/retention.ts`; Python adapters
own native filesystem locks and call it only after successful publication.
The adapter validates the complete analysis JSON with Python's file parser and
passes its exact size and modification time to retention. TypeScript verifies
that binding before deleting history; it does not reassemble a potentially
gigabyte-sized analysis into one JavaScript string. Missing or invalid manifests
cannot authorize deletion.

Interrupted builds whose current result has not been successfully refreshed
remain available for recovery. They are not automatically treated as completed
analysis. Diagnostic experiments under `.local/reports/` and `.local/cache/`
have separate lifetimes; analysis retention does not erase them.

## RGB storage

Decoded game, receptor and popup RGB streams are not cached. Pixel detectors
read the unchanged original recording when their source, geometry or detector
contract changes. Compatible note observations, compact spatial masks, counter
measurements and derived artifacts remain reusable independently. Input effects
and popup channels without measurements stay explicitly `not_measured`; a source
recording is not a completed measurement.

Keep review folders small: prose, selected images and links to the current
inspector. Do not copy complete play directories into `.local/reports/`.
