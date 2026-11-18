# Regeneration and replay maintenance

## Review a bounded play window

```sh
PIU_SKIN_JOBS=8 just _play-window 4MyMJse0L0g 13 59:11.138 59:49.733
```

Start and end accept absolute playback seconds, `MM:SS.sss`, or `HH:MM:SS.sss`.
The half-open window runs through native observation, tracking, coordinate
registration, physical and musical timing, judgment and hold evidence, UCS
transcription, and the interval review editor. A standalone summary links to that editor. It uses the play's saved
layout, skin bank and digit templates. Musical timing aligns the excerpt's
audio against the official reference. If timing or placement is unresolved,
the report retains the failure evidence. Each run publishes its own inspector
and available UCS draft under `.local/reports/play-window-*/`; the chart
repository receives no draft registration. Start `just editor` to open the
window from the source selector, inspect its automatic chart and download its
UCS draft.

Use `--observations-only` to save the native trace under `.local/runs/`. Pass
`--reuse-native RUN_DIRECTORY` to use that trace for a full report of the same
source, segment and interval.

## Full local regeneration

```sh
sh scripts/run.sh .venv/bin/python scripts/regenerate.py --jobs 3
```

This runs `just auto` over cached source IDs, without downloading media when each `raw/` directory contains one completed recording. Per-source logs and a report with exit status, elapsed time and before/after source metadata are saved in `.local/runs/regeneration-*/`. Failed sources do not prevent the remaining sources from running. The command exits non-zero if any source failed or changed. Keep concurrency low on GPU hosts to avoid loading multiple model copies into limited VRAM.

Source-time boundary comparisons use a one-microsecond floating-point tolerance.
Original PTS and playback values are retained without rounding or retiming.
Counter/row derivation has a separate `timing_format` contract: a timing-rule
change refits saved native observations and replays word reads without repeating
OCR or invalidating native appearance pixels.

The first native pass also retains exact counter-region RGB pixels in
`counter-pixels.npz`. Recovery and improved digit templates reuse these pixels;
legacy analyses acquire this small region once when needed. Source, geometry,
frame count and original timestamps are validated independently of digit reads.
Changing an association rule never invalidates this pixel cache.

A counter burst can be split only when every intervening value is independently
read with high confidence in the native pixels. Validate each resulting transition
against the ordinary capture-gap limit; a longer parent interval alone does not
invalidate short, fully observed substeps. A slow or absent substep, contextual
digit guess, reversal or unconfirmed ending keeps the original unresolved event.

Faded combo glyphs may fall below a fixed white threshold. When ordinary reads
fail, the reader measures neutral-pixel contrast with Otsu separation and tests
both that mask and a threshold halfway toward the usual white threshold. Both
must independently identify the same number with the existing template score
and ambiguity limits; the expected counter never selects this fallback. Reader
identity is part of the timing contract, so changes replay saved counter crops
while preserving native note observations. Legacy plays acquire this crop once.

A judgment-association upgrade with compatible saved word observations replays
those reads without refitting note trajectories. Reader/template changes retain
the isolated rebuild path; they must not rewrite the live observation trace
through the association-only fast path. Refreshed association contracts are
persisted even when no long-note or channel artifacts change.

`play/screen_regions.py` names known foreground HUD footprints.
`play/continuity.py` and `play/motion_warnings.py` audit native detection gaps,
premature endings, speed changes and possible stops independently of fit or
input success. See the [gameplay screen map](gameplay-screen-map.md). Their
versioned `visibility-diagnostics.json` is derived from saved frames without
decoding or OCR; replay refreshes an older diagnostic contract through report
generation. Generic timing exclusions do not suppress these checks.

Python adapters prepare acquisition objects for TypeScript `derived/tracks.ts`,
`derived/registration.ts`, `derived/fragments.ts` and `derived/clocks.ts`, which rebuild displacement
and subframe clocks from registered trajectory identities. Gap stitching and
its uniqueness checks run in TypeScript; Python only adapts acquisition tracks.
For a registered HUD gap, all intact approach coordinates constrain one shared
anchor interval. Every initial reappearance must intersect that same interval
under its own existing coordinate budget. A noisy endpoint cannot select the
anchor alone, and separate feasible anchors for separate frames do not prove
continuity. Conflicting references and competing successors remain separate.
Accepted registered connections retain their reference/reappearance coordinates,
original source PTS and common offset range in `fragment_connections`. `derived/beats/`
checks every co-observed neighboring head, including chords and close staggers,
against independent coordinate references; a small relative gap cannot exempt a
shared absolute timing error. It uses prepared official UCS timing and verified
alignment to test natural subdivisions. Missing references, failed shared
support and ambiguous beat rows remain explicit review states. Candidate refresh
selection also rejects a head independently observed moving sufficiently after
the refresh, using the same guarded passage check as confirmed associations.
Unverified, broad or temporally overlapping passage never proves this conflict.
Row recovery repeats its existing predicates until no further independently
supported match can be added. Each generation passes processing-conflict checks
before supplying anchors to the next; previously confirmed assignments stay
fixed. Ambiguous rows cannot bootstrap each other without an independent seed.
Additional matches retain their recovery generation and original evidence bounds. Native video,
frame traces and pixel caches are reusable across these derived-rule changes.

## Measuring scroll-speed changes

`just _chart-motion --sources VIDEO_ID --charts S23` estimates concrete speed
changes from saved shared native-displacement samples. It reads native
motion and verified source/alignment identities without decoding video, OCR or
new audio alignment. The default is read-only; `--write` appends qualified,
provisionally active effects to the separate chart repository. Measurements and
rejected-window reasons stay in `.local/reports/chart-motion/report.json` (or
an explicit `.local/` output path). Missing acquisition, changed media and
unsupported alignment fail explicitly; no proposal does not clear warnings.

The source filter includes all completed, registered recordings of a selected
chart, not only the recording that originally generated its draft. An alternate
recording needs its own reviewed explicit origin or source/window/reference-bound
audio alignment cache; the seed recording's origin is never copied. Missing or
stale alignment fails explicitly without downloading or decoding audio. Each
proposal retains the actual recording's identity and full alignment evidence.

The estimator compares approximately 300 ms linear displacement windows with
at least 12 native samples, 70% independent multi-lane support and sufficient
pixel displacement. Error bounds include fit error and a 1.5-pixel positional
floor. A phase-continuous intersection must agree with the intervening native
frames. Repeated render frames are tolerated without treating every stationary
sample as a stop. Automatic registration requires the current joint native-coordinate contract; older
integrated phases remain review proposals and cannot be written as chart effects.
It additionally requires at least three
peer heads, consistent longer native flanks (at least 400 ms on each side),
a relative ratio interval width of at most 15%, a native transition
bracket no wider than 100 ms and no other proposed change within 600 ms.
Gradual ramps, densely repeated changes, stops, reversals and sparse observations
can remain unresolved; they retain their original warnings.

`scroll_speed_change.speed_multiplier` is the measured **after/before screen
velocity ratio**, not an absolute game speed setting. Evidence retains velocities
in analysis pixels per second, lane spacing, original PTS, fit errors and the
nominal UCS BPM before and after. BPM ratio and measured ratio are separate;
neither a presumed half/double multiplier nor a musical grid replaces the
observations. Song-relative transition bounds include alignment uncertainty.

Pending and confirmed effects apply immediately. The concrete handler checks a
piecewise trajectory against each actual head before using it to inspect retained
processing pixels. Only matching native speed-change records are classified as
configured motion; chart reconstruction failures, missing input evidence, type
conflicts and contradictory motion remain warnings. Metadata recording preserves
human edits and rejected effects and deduplicates original-frame evidence.

## Bounded warning review

Use `just _replay --warning-limit 20 --jobs 8` to collect a small batch before
investigating and changing rules. Only current artifacts or successfully refreshed
plays contribute cases. The limit counts distinct unresolved warning cases collected
in this run, not newly introduced regressions or different warning kinds. Both recognition failures and unaccounted excluded trajectories contribute;
identical cases present in both files count once. Each
play contributes representatives of different reasons before repeated cases.
`warning-batch.json` retains the original records and report links; all remaining
cases stay in the original warning files. Collection neither acknowledges nor
suppresses anything. Repeated cycles deduplicate cases inside the run; a new run
still exposes unfixed cases.

At the limit the coordinator stops scheduling, lets active children finish, records
`warning_limit_reached` and exits, including with `--watch`. A parallel batch can
therefore finish more plays than strictly necessary. Review the queue, fix a general
rule or add a concrete chart-specific handler/annotation, run checks, and then start
the next batch. Missing or malformed warning artifacts fail explicitly. Omit the
limit only when a complete acquisition or contract refresh is intended.

After inspecting a queue, pass `--reviewed-batch PATH/TO/warning-batch.json` to
the next run (repeat the option for multiple inspected batches). Those identities
are excluded only from the new review queue, so the next batch can discover
additional cases. The original warnings, failure checks and totals remain intact;
previous inspection is never a recognition exemption. Keep unresolved inspected
cases in a local review log with their reason and follow-up. A batch file should
be passed only after inspection, not automatically marked reviewed on collection.

Beat reconstruction prepares verified reference-audio translation before fitting
rows, even when an existing chart has no region annotations or suspected effects.
`charts/audio.prepare_alignment` is shared by beat preparation and chart policy;
it reuses a matching seed, explicit origin or source-bound alignment cache.
Reference/current checks themselves remain read-only and never decode audio or
fetch reference files. Failed preparation remains an explicit beat warning with
the alignment error; it does not silently fall back to a guessed song origin.

`derived/registration.ts` refines registered displacement with a matrix-free
solve of the head-overlap Laplacian and robust native-position weights. It
runs on saved detections without numerical-library dependencies. Its diagnostics are
retained under `scroll_motion.coordinate_registration`; failed blocks cannot
provide shared distances, target clocks or automatic speed estimates. Native
source-position conflicts remain separate reconstruction warnings.

Font discovery reads the acquisition header before the top-level `notes` array,
rather than parsing other plays' trajectories and derived channels. Candidate
fonts still have to pass the same current-recording pixel validation; this I/O
optimization does not transfer counter values or weaken validation thresholds.
