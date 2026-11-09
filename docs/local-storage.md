# Local storage and analysis history

Original recordings live under `.local/data/SOURCE/raw/`. Native observation
traces, original source PTS, counter crops and pixel caches live beside each
current play result under `play/segment-NNN/`. Preserve these for later analysis
without reacquiring video. Image banks are versioned in the separate data
repository. Generated HTML and derived stage artifacts are reproducible consumers.
Promotion updates complete JSON path values atomically without reserializing
numerical observations. Files with no affected paths retain their exact bytes
and modification times; original media paths and JSON object keys stay unchanged.

Native observations are structured text, not compressed video. A frame can carry
several positive patterns and alternatives with independent region errors and
coordinates. Repeated comparisons and broad sampling expansions can produce
large JSON traces. A refit stages a complete copy of the existing analysis;
`frames.jsonl`, its immutable `frames.base.jsonl` baseline, derived JSON and HTML
can therefore occupy space in both the staged and current results. Failed work
can leave another copy. Disk requirements must account for these copies rather
than the size of the recording alone.

## Automatic retention

Successful metadata and play publication keeps the current directory and removes
all superseded `analysis.previous-*` and `segment-NNN.previous-*` snapshots, along
with abandoned builds for that canonical result. Successful metadata cache reuse
and cached play refreshes also apply retention. Unrelated segments, original
media and human-named directories are outside its scope. Symlink directories
are never followed for deletion.

Failed analysis does not trigger retention. A play without its saved native trace,
immutable baseline or report also keeps its history. Original recording paths,
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
