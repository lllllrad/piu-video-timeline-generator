# Local interval review editor

Build the shared DCM package and open an existing prepared play:

```sh
just editor-build
just editor SOURCE --segment 13
```

Open the printed loopback URL (default `http://127.0.0.1:4180`). Use `--port` to select
another local port. The server does not download, decode, OCR, infer, transcode or rewrite
recordings. It needs a completed `report-data.json` from play analysis.

## Shared package and reproducible checkout

`scripts/editor/dcm.json` pins the DCM repository and base commit. The build clones
`.local/dcm` if absent, checks its commit and unmodified package sources, compiles
`packages/chart-editor`, packs a tarball under `.local/editor`, and installs that tarball.
A different commit or modified package source fails before compilation. Use
`python3 scripts/editor/build.py --checkout .local/dcm-editor` for an isolated checkout.
No branch resets, commits or pushes are performed. Dependency installation can need network
access; the initial compiler can be bootstrapped without installing the root dependencies.

The DCM web Studio consumes the same package's exact beat arithmetic, tempo projection and
clipped note geometry. Its existing React editor and generation/evaluation features remain
separate. The video editor consumes the package's source-time review model and canvas
primitives. The package has no Python, React, media storage or model-provider dependency.
The package exposes a canvas entry point; it does not replace all of DCM's React shell.

The DCM extraction is committed upstream; no local source patch is applied. After an
intentional pin update, update the tarball dependency path in `package.json`, then run
`python3 scripts/editor/build.py --update-lockfile`. Normal builds use the frozen lockfile.
`package-build.json` records the source commit, tarball name and tarball hash.
Package/cache outputs stay ignored. QG's shadow-workspace wrapper copies only explicitly
listed local tarball dependencies, retaining pnpm's ordinary lockfile comparison.
The prepare script adapts QG's generated hook to use `scripts/run.sh`, so project-local
commands resolve during commits. Repeated installs preserve that hook, and existing
user-authored hooks remain unchanged. Hook installation is managed by dependency setup;
QG automatic installation is off so it cannot replace the environment wrapper. Staged
rules and all configured commit checks remain enabled.

## Review model

Each review has its own ID, revision, original source identity, prepared-analysis fingerprint
and explicit recording-time coverage interval. Store files under:

```text
.local/data/SOURCE/play/segment-NNN/review/
  index.sqlite
  intervals/REVIEW_ID.json
  intervals/history/REVIEW_ID/000001.json
```

Truth belongs to the selected interval, not an entire song. Changing the inspection window
does not silently change existing truth coverage; choose **New review** to create truth for
another interval. Unknown/censored head or tail times remain `null`. A hold crossing a
review boundary can retain its known endpoint and observed interval. Exact beat placement
is optional and must not be inferred from a recording-second edit.

The **Manual note** selector and **New note** action provide keyboard access to selection,
consecutive creation, correction and removal through the exact-time form.

Notes have stable per-lane IDs. Hold shape, nonuniform weighted ticks and scroll multipliers
are independent collections. Tick weights can be unknown; concurrent lanes do not multiply
a chart-wide count event. Scroll multipliers are independent of musical BPM. No UCS body row
creates a tick. UCS export cannot preserve all these facts and is not the canonical review
format. This editor currently saves its richer review JSON; it does not register corrected
charts or export edited review truth to UCS.

Copying an automatic observation is an explicit draft operation. Manual edits do not change
original detections, track identities, beat fits or input associations. **Reviewed** is an
explicit user declaration of independent interval review, not an inference from warning
counts. The head comparison uses only known targets inside coverage and a stated 50 ms
matching tolerance. It does not score hold tails, tick schedules, identities, scroll events,
physical inputs or whole-song accuracy. Missing automatic target times remain unresolved.

Saves require the original source identity, analysis fingerprint and current review revision.
Concurrent saves fail with HTTP 409. Earlier saved revisions are retained. Stale analysis
reviews remain readable and cannot overwrite a review against changed evidence.

## Bounded report delivery

Default report publication now writes a small HTML entry point rather than embedding the
prepared analysis. `just render INPUT.json OUTPUT.html` also produces a small entry point.
Existing large reports can be replaced with this render command without rerunning inference.
The legacy embedded renderer remains available explicitly for inspector runtime regressions.

The server streams prepared JSON into SQLite, retaining records individually with compressed
full details and compact summaries. Compact popup/receptor/motion rows are bound to their
saved original channel timeline. It never loads the complete prepared JSON into memory.
The index is disposable; interval truth is not. An individual evidence record is materialized
while indexing; index building is not a constant-size bound on arbitrary malformed records.

Queries are limited to 120-second windows and 500 records per page. The observation list
pages independently. The chart overlay is capped at 500 automatic note records per window;
a message asks the user to narrow crowded windows. Detail previews cap nesting and array
lengths. Original JSON/JSONL/image/mask artifacts remain available by explicit streamed
download. Video uses HTTP byte ranges over the original file. Browser codec support is
required; an error never triggers transcoding.

The server listens on loopback only. Writes require a per-process token, source binding,
revision checks and size limits. Evidence paths must remain inside the selected segment.
Use one server/port per play; report links validate source and segment before opening.

## Validation

Run `just check` for repository rules, both TypeScript checks, derived tests and native tests.
The review tests cover interval boundaries, censored holds, weighted ticks, compact-channel
source timestamps, unchanged source files, revision conflicts and bounded previews.
DCM's shared-package tests and existing beat/editor/playback tests validate extraction.
Browser tests use a Playwright container with the repository mounted read-only and only
screenshot artifacts writable; the local server stores test drafts explicitly as drafts.

Start the editor in another terminal, then run the browser smoke test:

```sh
just editor-browser http://127.0.0.1:4180
```

Docker uses the pinned Playwright image digest and installs its Node test package inside
the container's temporary filesystem. Chromium and its libraries are not installed on the
host. Screenshots and `browser-result.json` stay under `.local/editor/artifacts/`; the saved
smoke interval is clearly marked as an unreviewed test draft. The test checks keyboard-only
consecutive note creation, selection, correction and deletion as well as weighted ticks,
scroll changes, saved values, bounded channel queries and original-media Range responses.

## Inspection controls

Desktop keeps the recording, chart and independently scrolling review panel in one viewport.
The observation list pages forward and backward without loading a complete analysis.
**Previous interval**, **Next interval**, **At playhead**, and the view-size selector only change
the inspection window. Typing bounds does not change the chart until **Inspect interval** succeeds.
**Show review interval** returns to saved truth coverage; navigating never expands that coverage.
Comparisons are withheld when the view omits truth or automatic evidence is capped.

Click an automatic chart object to reveal its original saved evidence and recording position.
Copying remains an explicit draft operation. Clicking empty chart space seeks the recording;
Shift-click adds a manual tap. The exact-time form remains available for keyboard editing.
Space toggles playback, Left/Right step original observed frames, Shift+Left/Right move the
window, Ctrl/Cmd+S saves, and Ctrl/Cmd+Z / Ctrl/Cmd+Shift+Z undo/redo. Native input controls
retain ordinary typing and selection shortcuts. Undo changes draft content without rewinding
the saved revision. A save response never discards edits made while that save was in flight.
