# Local storage and analysis history

Original recordings live under `.local/data/SOURCE/raw/`. Native observation
traces, original source PTS, counter crops and pixel caches live beside each
current play result under `play/segment-NNN/`. Preserve these for later analysis
without reacquiring video. Image banks are versioned in the separate data
repository. Generated HTML and derived stage artifacts are reproducible consumers.

Native observations are structured text, not compressed video. A frame can carry
several positive patterns and alternatives with independent region errors and
coordinates. Repeated comparisons and broad sampling expansions can produce
large JSON traces. A refit stages a complete copy of the existing analysis;
`frames.jsonl`, its immutable `frames.base.jsonl` baseline, derived JSON and HTML
can therefore occupy space in both the staged and current results. Failed work
can leave another copy. Disk requirements must account for these copies rather
than the size of the recording alone.

## Automatic retention

Successful metadata and play publication retains the current directory and one
most recent `analysis.previous-*` or `segment-NNN.previous-*` rollback. Older
snapshots and abandoned build directories for that same canonical result are
removed after the new result is published. Successful metadata cache reuse and
cached play refreshes also apply retention. Unrelated segments, original media and human-named directories
are outside its scope. Symlink directories are never followed for deletion.

Failed analysis does not trigger retention. A play without its saved native trace,
immutable baseline or report also keeps its history. Original recording paths,
including symlink targets, protect containing directories from removal; this can
retain more than one rollback when a recording was placed inside a snapshot.

Publication remains protected by the source/segment writer lock. A shared
`.retention.lock` additionally pins snapshot selection and staging while another
segment reuses a saved observation snapshot. Pruning takes the exclusive side of
that lock, after staging has completed. Long-running inference does not hold the
history lock. Retention is implemented in `derived/retention.ts`; Python adapters
own native filesystem locks and call it only after successful publication.

Interrupted builds whose current result has not been successfully refreshed
remain available for recovery. They are not automatically treated as completed
analysis. Diagnostic experiments under `.local/reports/` and `.local/cache/`
have separate lifetimes; analysis retention does not erase them.
