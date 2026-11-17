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
