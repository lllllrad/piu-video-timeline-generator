# Validation

## Automated checks

Run `just check` offline. The suite covers environment isolation, input preparation, synthetic media probing, review validation, safe output creation, timestamp rendering, non-zero container origins, actual sampled-frame PTS, synthetic HUD matching/refinement, multiple HUD profile merging, positional OCR parsing, conflicting player badges, multi-frame agreement, and evaluation integrity. Synthetic checks verify mechanics, not PIU accuracy. Run `just check-ocr` separately for the native macOS Vision engine.

Validation host: macOS 26.5.1 (25F80), native Vision. Host OCR results may vary with OS/Vision versions.

Historical artifact names below that start with `outputs/` now live under `.local/outputs/`; the names are retained in this report to identify the original runs.

## Analysis/presentation separation validation

Three additional unlabeled recordings (`jYuRHc_D8zY`, `7BLKTVDLeYo`, and `J0f9V-Qpijs`) were analyzed after adding bounded similar-title agreement, unique summary-row recovery, corroborated single-result titles, and earlier selection sampling. Their final 14, 18, and 6 detected segments respectively contain no null song or chart fields. This is a missing-field result, not proof that all 38 strings, chart labels, or detected segment counts are correct. The rendered outputs retain 2, 5, and 1 review-flagged entries respectively for boundary or evidence reasons. The user supplied `7BLKTVDLeYo` twice, so four input lines represented three unique videos.

`just check` passes 78 tests after separating analysis from output. Regression coverage checks analysis with and without judgments (including explicit `--no-judgments`), absence of presentation files, explicit enrichment rendering, legacy JSON compatibility, repeated JSON-only rendering, input preservation, and successful analysis remaining available after a presentation failure.

The existing 145-second derived local test clip was processed with `just analyze .local/tmp/judgments-cli-sample.mkv .local/outputs/analysis-separated-v1 --judgments` using real Vision OCR. It produced one play and `analysis.json`, with no `timeline.json`, `timeline.txt`, `details.txt` or `rendered.json` in the analysis directory. Its timing, song/chart and all seven P2 numeric fields matched the earlier combined workflow fixture. The same analysis was rendered twice without OCR into `.local/outputs/analysis-separated-report-v1/` (bundled conditional template) and `.local/outputs/analysis-separated-report-v2/` (one-off detail template). This is a workflow regression, not new recognition-accuracy evidence; the derived clip has local test timestamps, not publication-ready original-video timestamps.

## Player judgment and template validation

The optional result extension was exercised through `just results` on all 30 existing segments of the second recording (`outputs/judgments-full-v1/`). It detected one result slot in 28 plays and retained empty/unknown result data for two failed plays without usable result screens. All five judgment fields were populated in those 28 slots; five scores and one max-combo value remained unknown. This is a completeness count, not an accuracy measurement for all 140 judgment values.

Six result screens were directly read to check numeric accuracy, covering right single/double and left basic/double results. All 42 numeric fields below (five judgments, max combo and score per play) matched the OCR output. Most of these examples informed implementation, so this is development validation, not an untouched benchmark.

| Original segment | Slot | PERFECT | GREAT | GOOD | BAD | MISS | Max combo | Score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10 | P2/right | 1099 | 57 | 12 | 5 | 39 | 281 | 933848 |
| 18 | P2/right | 439 | 7 | 0 | 0 | 0 | 446 | 993753 |
| 19 | P1/left | 765 | 34 | 8 | 4 | 14 | 346 | 951749 |
| 23 | P2/right | 895 | 8 | 0 | 0 | 2 | 367 | 991310 |
| 25 | P1/left | 298 | 19 | 2 | 1 | 0 | 307 | 968392 |
| 26 | P1/left | 621 | 14 | 0 | 0 | 7 | 429 | 978813 |

Evidence comes from the original game-only result frames under `outputs/auto-heldout-v4/evidence/` and the enlarged crops/raw numeric OCR under `outputs/judgments-full-v1/evidence/`. Numeric-only score crops initially caused reversed digit recognition; retaining the SCORE-label context corrected the inspected case. Bright-text isolation in count columns removed background letters that had merged with zero digits. Unknowns are not coerced to zero.

`outputs/judgments-verified-v1/` exercises enrichment of selected segments; `outputs/judgments-rerender-v1/` exercises JSON-only re-rendering with the same selected-player placeholders across P2 and P1 plays. `outputs/judgments-p1-v1/` confirms that explicitly selecting an absent P1 prints unknowns/warnings rather than using P2's counts. Conditional missing-count behavior, first-match rules, separate player namespaces and two-player selection are covered by unit tests. Native OCR also reads distinct left/right counts from a synthetic simultaneous two-player result fixture. Genuine simultaneous two-player recordings have not yet been validated.

The complete `just auto ... --judgments` flow was additionally exercised on a 145-second derived local test copy (`outputs/judgments-auto-cli-v1/`). It produced the title/detail files. This copy is only a CLI fixture, not a retimed replacement for the original recording or a publishable original-video timeline. Its source recording was left intact. CV game-screen localization is not part of this extension.

## Automatic pipeline evaluation

The URL-input workflow was exercised on `uqM7H-OJp68`, reusing the intact downloaded media. The local-input workflow performs no network request. All image OCR runs locally on the game crop, excluding chat and cameras. No comments were used as detector inputs or evaluation labels.

The first development recording (`_OE47GBOvB0`, 4088.333 seconds) was surveyed across its full duration with game-only 10-second keyframe sheets. Titles/charts were read directly from selection, result and failed-play summary screens. The final selective-preprocessing run `outputs/auto-seed-v6/` matched all 15 reviewed segments and all 15 song/chart pairs, with no unknown labels, as recorded in `outputs/seed-evaluation-v6.json`. This is development-set performance, not an untouched benchmark. Broad review timing ranges do not establish frame-exact timing accuracy; the first boundary pair was additionally inspected at 0.1-second spacing.

The second recording (`uqM7H-OJp68`, 8656.766 seconds) was independently surveyed using all seven game-only 20-second keyframe sheets. Direct review found 30 plays, including single-mode and basic-mode plays missing from the initial detector. Result images were read for labels, including left-side badges. The source-bound reference is `data/derived/heldout-reference.json`.

Initial automatic results (`outputs/auto-heldout-v1/`, before alternate HUD discovery) matched 26/30 plays, with four misses and no false positives in the surveyed reference. Song labels were correct for 21/30 reviewed plays and chart labels for 20/30; four detected songs and six detected charts were unknown. One accepted title incorrectly included dim background-video credits. These are measured failures, not merely low-confidence warnings. See `outputs/heldout-evaluation-v1.json`.

The second source subsequently informed fixes for centered STAGE HUDs, left/right result badges, basic-mode labels, delayed results and background-text contamination. Consequently, post-fix results on it must be described as source-separated development validation, not untouched holdout accuracy. The multi-HUD run `outputs/auto-heldout-v2/` recovered all 30 surveyed plays. The final `outputs/auto-heldout-v4/` run matched all 30 reviewed segments and all 30 song/chart pairs, with no unknown labels, as recorded in `outputs/heldout-evaluation-v4.json`.

The unconditional white-title preprocessing run `outputs/auto-heldout-v3/` matched 30/30 intervals and charts, but only 27/30 song labels (two unknowns, one I/1 confusion). On the first source, `outputs/auto-seed-v5/` regressed to 14/15 song labels while retaining 15/15 intervals/charts. These runs are not final outputs. Selective preprocessing subsequently recovered the `404 (뉴 에라)`, `슈퍼☆하라구로☆팝`, and background-credit `디기탈리스` cases in dedicated real-frame reruns (`outputs/title-regression-v4/`), each with multiple agreeing frames. Latin-only OCR read `R.I.P.` correctly in four tested original title patches; language routing was added without a song dictionary and verified in the final second-source run.

Final local artifacts (ignored by Git):

| Recording | Automatic output | Evaluation | Matched plays | Correct songs/charts |
| --- | --- | --- | --- | --- |
| `_OE47GBOvB0` | `outputs/auto-seed-v6/` | `outputs/seed-evaluation-v6.json` | 15/15 | 15/15 each |
| `uqM7H-OJp68` | `outputs/auto-heldout-v4/` | `outputs/heldout-evaluation-v4.json` | 30/30 | 30/30 each |

Both final outputs have zero reviewed misses, false positives or unknown labels. Label comparison normalizes Unicode, whitespace and case; it does not correct words, punctuation or chart levels. JSON/text consistency, unchanged source size/mtime and existence of all 546 OCR evidence frames were checked. The second run refined all 60 boundaries; six segments still carry low-confidence review flags despite matching the reference. Review flags are deliberately retained. These outputs are local-playback timelines, with no silently asserted YouTube offset.

Additional boundary inspection (`outputs/alternate-boundary-review/`, 0.1-second decoded-frame samples) brackets the S13 play start at 4952.3–4952.4 and end at 5060.6–5060.7 seconds. The basic-mode Winter play starts within 7140.1–7140.2 and ends within 7225.1–7225.2. Automatic v2 values are 4952.4/5060.7 and 7140.2/7225.1 respectively. This supports the documented one-sample quantization allowance for these examples, not a universal 0.1-second accuracy bound.

Review ranges deliberately include survey/keyframe uncertainty. A 10/20-second survey cannot rule out every shorter missed play, and zero distance outside broad ranges is not zero timestamp error. The evaluator rejects missing source identity, non-finite ranges, overlapping annotations and predictions crossing review coverage instead of silently excluding them. None of these recordings establishes accuracy for arbitrary camera captures, HUD skins or other game versions.

## Earlier real-video smoke test

Seed `_OE47GBOvB0` was downloaded with the normal fetch workflow. The merged file is 1920x1080 H.264 at a reported 60 fps; video packet timestamps cover 4088.333 playback seconds. The previously saved YouTube metadata reports 4091 seconds. This discrepancy is not evidence of a constant offset: no YouTube alignment has been asserted. The original downloaded media is left intact and ignored by Git.

The inspected layout contains a game region on the left, a separate camera region below, and chat/camera content on the right. Only the small static STAGE label in the game HUD was used for the experimental matcher (`x=180, y=0, width=76, height=20`, reference at 140 seconds). Chat and comments were not detector inputs. Default parameters over the full recording produced 15 unreviewed candidates. Result/failure screens were visually spot-checked after those candidates. This is not a measurement of precision or recall; missed sections have not been exhaustively annotated.

The first candidate was independently checked with direct frame sampling near its start and end. The HUD matcher proposed 126–260 seconds; the visual transition is bracketed by 124.7–124.8 seconds and 258.3–258.4 seconds. This demonstrates why keyframe-grid proposals must not be treated as exact boundaries. The sampled upper bounds were used to exercise the reviewed JSON/text exporter. The song and chart were read from loading/result screens, not inferred from comment labels.

Local artifacts (not committed):

- `outputs/seed-candidates.json`: all 15 unreviewed proposals and matching scores.
- `outputs/seed-results/`: post-candidate screenshots and source timestamps.
- `outputs/seed-first-fine/`: 0.1-second transition samples for the first song.
- `.local/seed-review.json`: a partial, first-song-only review.
- `outputs/seed-reviewed-sample/`: first-song JSON/text smoke-test output, on the local timeline only.

## Further validation and limitations

- Exhaustively annotate short plays beyond the survey-grid coverage; keep those limits explicit until then.
- Validate additional layouts, HUD skins, edits, variable frame rates, long keyframe intervals and camera-only recordings. Current real-video validation covers the tested Phoenix panel and its double, single, basic and left/right result layouts.
- Extend validation to untouched recordings before claiming generalization. Automatic OCR is implemented, but engine confidence and multi-frame agreement are not calibrated correctness probabilities.
- Verify local-to-YouTube alignment visually before publishing timestamps. Do not infer an offset from the duration discrepancy or silently shift the local timestamps.
- Retain unknown fields and human review until accuracy has been measured on an independent set. Chart/replay extraction remains outside the current timeline generator.
