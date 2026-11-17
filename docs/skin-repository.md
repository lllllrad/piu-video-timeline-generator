# Versioned skin repository

## Versioned reference assets

Keep reusable banks in the separate chart-data repository (`../piu-chart-data`,
or `PIU_CHART_DATA_DIR`). Build and inspect candidates locally, then publish:

```sh
just skins publish .local/cache/note-skins/example/bank.json --revision v1
just skins list
just skins select SOURCE --segments 1 3 --skin example --revision v1
just skins validate
```

`--repo PATH` on each management command selects a different data repository.
Initialize it with `just charts init` first. Publication copies only the bank and
its referenced PNGs, preserving exact bytes and source/calibration provenance.
The bank's own `skin` field supplies the identity; `example` above must match it.
Assets live at `skins/banks/<skin>/<revision>/bank.json` with the referenced PNGs
and `reference.json`. The latter binds the complete bank content hash and records
`experimental` (default), `reviewed` or `unsupported` status plus an optional
`--description`. Review status never replaces the native calibration checks.
Conflicting publication requires a new revision; repeating identical publication
is harmless. Commit these files in the data repository. Analyzer code and
synthetic tests remain in this repository; recordings and generated diagnostics
remain local. Absolute source-image paths inside provenance are historical
references; loading the published bank requires only its bundled PNGs.

Persistent selections live in `skins/sources/SOURCE.json` in the data repository:

```json
{"schema":1,"profiles":[{"segments":[1,3],"bank":{"skin":"example","revision":"v1"}}]}
```

Profiles retain optional `role_clearance` settings alongside the selection.
`select` replaces only the specified segments; settings for remaining segments
are preserved. A shared source profile takes precedence over the legacy local
`.local/data/SOURCE/note-skins.json`; absent segments in that shared profile have
no skin selected. The explicit `--note-skin PATH` play option overrides either
profile. Legacy local string bank paths remain relative to the source directory.
Missing assets, changed published bytes, unsupported selected revisions and
duplicate segment selections fail explicitly; they never fall back to outlines.
`validate` checks image geometry, content binding and all shared selections.

Existing local bank locations may be symlinks to published assets so saved
observations can still verify their original references. Change a published bank
by building and publishing a new revision, then selecting it. Moving identical
bank bytes preserves acquisition identity and needs no native re-detection.
Bank/image bytes and detector rules participate in
cache identity. A changed bank rescans source RGB without metadata OCR, retaining
counter observations and original PTS. The current threshold-plane cache cannot
reconstruct RGB; image detection changes can therefore reread original media.
Replay groups competing tap/start/end references together for each lane kind,
with separate body groups for each kind. A changed direction reacquires that
kind on both player sides; unchanged directions keep their native observations.
Merged observations recompute body-pattern ownership against all cap images.
Unchanged groups are reused only when
the acquired bank is still available with its original identity, the detector
rules and spacing agree, and all ordered reference measurements in that group
are identical. Body-only updates scan body images without repeating cap search.
Proven metadata-only reference updates reuse all groups without decoding. An
unverifiable old bank or changed detector rules require fresh acquisition.
Missing native image observations or invalid source timestamps fail explicitly.
Image-bank changes preserve source timestamps and counter observations while
replacing note observations from RGB references. Image-to-image updates reuse
unchanged template groups. Removing a selection leaves that play unsupported;
existing reports remain readable and new analysis requires a selected bank.

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
