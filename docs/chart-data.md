# Editable chart data

The official [catalogue PDF](https://ucs.piugame.com/sample_download/pdf.php) identifies each song by a UCS code. A ZIP such as [CS349](https://ucs.piugame.com/sample_download/zip.php?ucs_index=CS349) supplies an empty UCS timing skeleton and reference music. The skeleton does not supply the game's note arrangement.

## Repository and workflow

```sh
just charts init
just charts list 'Switronic'
just charts add SOURCE --segment 20 --ucs-index CS306
just charts sync
just charts refresh-catalog
```

`init` creates a separate local Git repository at `../piu-chart-data`, preserving existing files. It does not publish a remote. `PIU_CHART_DATA_DIR` or the global `--repo PATH` option selects a different location. Commit and review chart edits in that repository independently of analyzer code. Its layout is:

```text
catalog.json
aliases.json
timing/CS306.ucs
charts/CS306/D22/phoenix/chart.ucs
charts/CS306/D22/phoenix/metadata.json
```

Once initialized, successful `just play` runs register missing charts automatically, including compatible cached analyses. Registration never overwrites an existing chart directory. Download, identity or alignment failures write a pending reason in the play's `chart-registration.json` without invalidating its native analysis. `sync` attempts registration for completed local plays; it does not invoke metadata OCR or acquire gameplay frames. It may download missing reference archives and decode audio for alignment.

An exact normalized catalogue title or an explicit alias must identify one code. There is no guessed translation or fuzzy title correction. Assign a title with `just charts alias 'VIDEO TITLE' CS349`, or pass `--ucs-index` to `add`. Multiple arrangements use different mode/level directories; game updates require an explicit `--revision NAME`. A UCS code identifies a song, not a chart difficulty.

## Timing and notes

Audio alignment compares 24 frequency bands in three independent reference windows. At least two windows must have strong, unambiguous correlation and agree within 40 ms. Alignment is translation only; mismatched, repeated or missing music stays unresolved. `add --song-start SECONDS` permits an explicit reviewed origin in original local playback seconds. Source size and mtime must match saved observations before automatic audio alignment and remain unchanged afterward.

UCS `Delay` is applied in milliseconds at each section boundary, while `BPM` and `Split` determine row duration. Subdivision expansion preserves every original row position and section duration, including BPM changes. The draft uses the least common multiple of each original Split and 48; this is a fine editable grid, not evidence of the intended musical subdivision. Metadata retains observed ranges and placement residuals. Unsupported directives and overlapping timing sections require manual handling.

Detected note geometry supplies chart notes independently of successful input/judgment association, so missed inputs do not remove notes from the draft. Hold-aware projection suppresses hold body/tail detections as separate taps and emits `M`/`H`/`W` cells. Single and Double use five and ten columns respectively. Conflicting same-lane placements, unbounded fits and censored hold endpoints are recorded as unresolved. The template cannot reveal notes absent from the observations.

Generated metadata explicitly records `review_status: unreviewed_draft`, source ID/segment, source identity, analysis fingerprint, timing source/hash, alignment evidence and placements. These drafts must not validate the same recording from which they were extracted. A human can edit `chart.ucs` directly and mark metadata reviewed after independent checking. Normalized timing-template hashes identify parsed timing content, not original ZIP bytes.

## Downloads

ZIPs, PDFs and music remain under `.local/cache/ucs/`; no archive member is extracted to an archive-controlled path. Size limits and expected UCS/music members are checked, and HTML login/error responses are rejected. HTTPS certificate and hostname verification remain enabled. Anonymous SSO cookies are kept in memory only; one retry of the original URL handles the site's malformed first callback. `PIU_UCS_CA_FILE` can supplement the trust chain when the server omits intermediate certificates; a locally provisioned `intermediates.pem` in the UCS cache is also recognized. No credentials or session cookies are stored with chart data.
