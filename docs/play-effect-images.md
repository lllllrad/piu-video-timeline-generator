# Effect images in play analysis

Select a sequence reference explicitly for a single play:

```sh
just play SOURCE --segment N --effect-reference .local/reports/REFERENCE/results.json
```

The reference must be schema 2 output from the
[RGB reference extraction tool](effect-reference-extraction.md). Selection is
retained in the play's `analysis.json`; later compatible play refreshes reuse it.
Use `--clear-effect-reference` to stop using the saved selection. A single
explicit reference cannot be passed to `--all`, because source identity does not
prove that different segments use the same skin.

References are currently bound to their original recording and segment, not a
certified portable skin identity. The adapter checks source size/mtime, reference
capture hashes, producer versions and receptor geometry. Legacy experimental
captures without a saved ROI must additionally reproduce an original RGB crop
from the current source/ROI. Foreign or changed references fail explicitly.
No automatic skin-name inference installs an effect reference.

## Acquisition and interpretation

The Python adapter reuses saved receptor and note timelines, decodes original
media with original PTS, and stores receptor-local RGB crops plus conservative
note/body exclusion envelopes. It acquires all off-to-on candidates and bounded
rebrightening candidates, including boundary-bright candidates. Unlike reference
sampling, play acquisition does not select twelve examples per direction. These
candidates are not ground-truth button presses. Frames outside candidate windows
remain unmeasured, not negative detections.

Overlapping windows share the same stored lane/frame crop. Acquisition is cached
independently of references and note/popup interpretation. Original recordings
are never rewritten. Producer or native trace changes invalidate acquisition;
reference/model changes reuse compatible saved crops. Changes in interpreted
notes or popup events recompute links without decoding or repeating image
measurement. Crop hashes and measurement trace hashes are checked on reuse.

TypeScript loads only supported training reference sequences. Full-play matching
first proposes positions/times with sampled RGB, then validates up to sixteen
proposals per reference at full crop resolution, including masks, raw/retained
RGB error, ordered RGB changes and reversed/constant controls. This bounded
search is distinct from the reference tool's exhaustive local search. An
`ordered_image_candidate` is conditional evidence within that search, not an
exact or independently calibrated animation age.

Every captured frame retains its original PTS, playback time, receptor-prior plus
RGB-translation origin, reference-stage alternatives, visible support and possible
local contamination regions. Receptor-prior localization is not independent
accuracy measurement. Reference stage seconds are relative to a training marker,
not physical button time. Source overlap with training windows is marked; counts
are not held-out recognition accuracy.

## Play associations and reports

The main play report links to `effect-images/report.html`. It exposes all image
windows, ambiguity, note candidates and these downloadable artifacts:

| Artifact | Contents |
| --- | --- |
| `effect-images/acquisition/capture.json` | Source identity, crop indices, geometry and original frame clocks |
| `effect-images/acquisition/pixels.rgb` | Deduplicated 47 x 47 RGB crop evidence |
| `effect-images/acquisition/exclusions.bin` | Conservative native exclusion envelopes |
| `effect-images/events.json` | Sequence decisions and measurement dependencies |
| `effect-images/observations.jsonl` | Per-window native-frame positions and reference-stage candidates |
| `effect-images/associations.json` | Note/popup candidates and unresolved relationships |
| `effect-images/summary.json` | Bounded report fields and artifact links |

Association uses lane and observed note visibility, with a qualified 150 ms
post-visibility allowance. It is a candidate search, not an input-latency
calibration. Multiple notes, overlapping effect windows, unknown note types and
censored/unresolved holds prevent unique tap corroboration. Popup candidates
remain separate and do not consume or reassign an existing judgment event.

Prepared notes retain `effect_image_candidates`; existing popup matches can carry
`effect_image_corroboration` for unique tap-image candidates. The standalone
channel is also exposed as `visual_channels.effect_images`. These fields do not
change target times, raw offsets, grades, existing event ownership or coverage.
`physical_input_range` stays null. The observations provide inspectable supporting
evidence while display/input delay and ambiguous phases remain unresolved.

## Performance and concurrency

Plays still run sequentially. Independent effect windows use up to eight Node
worker threads by default. `PIU_EFFECT_JOBS=1..32` overrides the effect pool;
otherwise it follows `PIU_SKIN_JOBS`, then the available-CPU default capped at
eight. RGB and exclusion bytes are shared read-only between workers. Each worker
has a bounded one-window task, and the coordinator restores source event order
before stable frame sorting. A worker failure aborts measurement and terminates
the remaining workers. Changing concurrency alone does not invalidate cached
measurements or change their numerical meaning.

Association queries use inclusive lane/time indexes and preserve original note,
popup and event ordering. Per-frame JSONL is written incrementally rather than
building a second full serialized copy. Python attaches note links through a
reverse index instead of rescanning every relation for every note.

`inspection-performance.json` records elapsed time and completion/failure for
native input preparation, evidence compaction, frame loading, configured pixel
measurement, derived inspection, materialization, JSON reading and effect
analysis. These diagnostics do not participate in evidence or cache identity.
The remaining large inspection JSON files and temporally dependent hold/tracking
steps are not made parallel by the effect pool.

A local saved-data comparison on 2026-11-18 measured 32 RGB windows at 16.77 s
with one worker and 7.96 s with eight workers (including pool startup and pixel
sharing). Full event and per-frame outputs were identical. For 3,063 image
windows, association time changed from 2.105 s to 0.029 s with identical output.
Projecting the saved association request reduced 16,399,312 bytes to 171,134 bytes
while preserving all 3,063 associations. These are local component measurements,
not whole-play speed estimates or recognition-accuracy validation. Large original
`frames.jsonl`/`frames.base.jsonl` snapshots retain their existing storage contract.

Native hold endpoint pairing also groups eligible tails by lane and reuses each
endpoint's observed-position table. Pair ordering and temporal continuity checks
remain unchanged; the state-dependent hold pipeline still runs in source order.

See [native frame results](native-frame-results.md) for the stage boundary that
keeps full image comparison searches out of ordinary tracking input.
