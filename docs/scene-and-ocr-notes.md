# Scene, layout and OCR field notes

This is reusable implementation knowledge from the first milestone, not a universal PIU specification. Observations cover the two Phoenix recordings listed in [validation](validation.md). Current behavior refers to commit `7865c69`; proposed changes belong in [the next-step design](layout-and-result-design.md).

Later implementation update: optional player-separated judgment OCR and templates are now available. The first-milestone descriptions below remain a historical record, including statements that counts/player slots were not yet implemented. For current behavior, field names and limitations, use [result/template usage](result-templates.md).

## Scene progression

The useful working sequence is song/chart selection, loading or song introduction, gameplay, transition, and a per-song result. The recording may then return to selection or show a multi-song `PLAY RESULT` summary. A failed play can instead lead through a failure message and a summary without a usable per-song result. Menus, pauses, attract/demo footage and stream-only content can occur between sessions. This is an observed working model, not an implemented full scene classifier or an exhaustive transition graph.

| Scene | Useful evidence | Important trap |
| --- | --- | --- |
| Selection | Centered song title, expanded chart badge, sometimes compact D/S badge | Browsing can show a different song shortly before the actual selection. A row of available levels is not necessarily the selected level. |
| Loading / introduction | Song art, title or credits | Not yet gameplay; background credits are not reliable title labels. |
| Gameplay | Static `STAGE` word near the top, receptors/gauge | HUD position changes with play layout. The stage number changes; match the word, not the number. Demo/attract content needs separate negative examples. |
| Transition / black frame | Gameplay HUD disappears | A result may not be visible immediately. Use the gameplay boundary for the timeline, not the later result timestamp. |
| Per-song result | Centered title, chart badge, SCORE and judgment rows | Player information can be left or right; overlays can obscure the result. Background animation remains visible behind text. |
| Failure screen | Failure message, e.g. `HEY!` | Do not accept message text as a song title. No usable score result is guaranteed. |
| Multi-song summary | `PLAY RESULT`, multiple song rows and chart badges | It contains previous plays too. Do not attach the first readable row to the latest play. |

The current implementation does not track this whole sequence. `scripts/auto_timeline.py` detects HUD intervals and samples relative to their boundaries:

- Selection: start minus 8, 6, 4 and 3 seconds.
- Result: end plus 3, 5, 7, 8, 9, 10, 11 and 12 seconds.
- Summary fallback: end plus 12, 14 and 16 seconds, only when a song is known but its chart is unknown.

These offsets worked on the tested material; they are not game timing constants. A future scene tracker should locate stable screens instead of assuming these windows always contain the right scene. Do not sample into the next play and assign its result to the previous play.

`is_result_screen()` currently requires `SCORE` plus at least one of `PERFECT`, `MAX COMBO` or `KCAL` after text normalization. This prevents the observed failure-message/title error, but OCR can miss a marker and reject a genuine result. Selection sampling does not yet have an equivalent full scene gate.

## Player side and result layout

Player-dependent P1/P2 layouts require both sides to be supported. Directly observed: the chart badge, score/grade and judgment values can occupy the left or right part of the result screen while the title stays centered. Judgment labels may remain near the center while their associated values move to the active side. Do not mirror the entire screen or assume every field uses the same transform.

Keep three concepts separate: the image-side slot (`left`/`right`), the logical game player (`P1`/`P2`), and the person being analyzed. The current code reads both chart-badge regions, but does **not** establish player identity, output a player identifier or follow a player across scenes. Do not treat its single chart value as proof of P1/P2 attribution. A profile can declare a verified side-to-player mapping; mirrored captures and unfamiliar layouts require renewed verification.

Current result parsing accepts a chart only when recognized full-size badges agree on one chart value. Different left/right charts yield an unknown chart for that frame; identical values do not prove there was only one player. There is no multi-player result model yet. Simultaneous two-player screens, independent player failures, and transitions between one/two players need additional labeled tests before support is claimed.

For future score extraction, bind the chart, score, grade and judgments to the **same result slot and play interval**. Never combine a left-player chart with right-player judgment numbers. Double mode is a chart mode, not evidence that two players are present.

## Coordinate conventions and current regions

The default game rectangle is the top-left 1300x730 area of a 1920x1080 source. It excludes the camera below and chat/camera content to the right. `--game-roi x,y,width,height` overrides it in source pixels. Internal OCR boxes are normalized to the cropped game image, with origin at the top left. Focused OCR is mapped back into that space. Do not confuse source pixels, game-relative fractions and enlarged OCR-image coordinates.

The following are current implementation crops, not a calibrated layout schema. Each tuple is `(x, y, width, height)` relative to the game image; see `focused_lines()` in `scripts/recognition.py`.

| Region | Normalized crop |
| --- | --- |
| Result title | `(0.20, 0.15, 0.60, 0.07)` |
| Result chart, right | `(0.59, 0.25, 0.15, 0.14)` |
| Result chart, left | `(0.26, 0.25, 0.15, 0.14)` |
| Selection title | `(0.20, 0.485, 0.60, 0.052)` |
| Selection expanded charts | `(0.15, 0.63, 0.70, 0.30)` |
| Selection compact chart | `(0.07, 0.82, 0.15, 0.17)` |
| Summary titles | `(0.25, 0.14, 0.45, 0.80)` |
| Summary charts | `(0.70, 0.14, 0.09, 0.80)` |

The parser also has positional constraints separate from these crops: result-title centers at y=0.13–0.23, selection-title centers at y=0.48–0.54, and mode/level proximity checks. Moving only the crop constants would not make the layout configurable. Both acquisition regions and parsing constraints must migrate together.

The STAGE patch moved from approximately x=180 to x=613 in the tested 1300-wide panel. Single and basic-mode examples used the centered patch; gameplay lanes could be on either side. The automatic path discovers an initial patch in the first ten minutes, then samples uncovered portions every 30 seconds for new positions. It can find additional HUD positions but does **not** automatically locate an arbitrary game panel or infer a complete result layout. Short appearances between samples and new appearances at an already known position with a different skin remain limitations.

## Recognition lessons

- Prefer a confirmed result over selection for the played chart; selection can be changing. Current song and chart consensus are selected independently, so their evidence can come from different phases. Future player-aware results need stronger joint association.
- Keep at least two agreeing frames, with ties unresolved. Repeated identical pixels can repeat the same OCR mistake; agreement is not calibrated accuracy.
- Use enlarged title/chart crops. Korean/English title OCR and English chart OCR performed better than using one recognition language for all regions. Numeric badge text was sometimes interpreted as Korean glyphs.
- Preserve the original title image first. Unconditional bright-text thresholding damaged thin glyphs and stars in `404 (뉴 에라)` and `슈퍼☆하라구로☆팝`. Selective isolation removed dim background credits attached to `디기탈리스`; English routing resolved the I/l/1 ambiguity in `R.I.P.`. These are regression cases, not a replacement dictionary.
- `PUMBILITY LEVEL UP!!` can cover title/result information. Results and their readable labels are not necessarily available at the same offset after every play. Resampling later is preferable to accepting overlay text.
- Store mode and level evidence together. A nearby score, option value or available-level row is not a chart level. The current full-word mode correction allows only one substituted glyph; do not expand it into unrestricted fuzzy guessing.
- Basic-mode badges visibly say `VERY HARD 12`. Preserve that displayed label; do not silently reinterpret it as `S12`. `COOP` is recognized by the parser but was not validated as a real-video mode in this milestone.
- The summary fallback matches a known title to a unique row and its nearby chart badge. Repeated occurrences of the same title make the row ambiguous; current code returns unknown instead of assuming the last row. It does not recover an unknown title from a summary.
- Failed plays can lack a usable per-song result. Missing statistics must remain missing, not zero; summary chart recovery is not recovery of the full judgment table.

## Judgment counts: observed versus implemented

Result frames visibly contain `PERFECT`, `GREAT`, `GOOD`, `BAD`, `MISS`, `MAX COMBO`, `SCORE` and `KCAL` in the inspected layouts. Raw OCR can contain these strings and numbers, but the current final JSON exposes **no parsed or validated judgment counts, score, grade or calories**. The result gate reads labels, not the associated values. Do not build a report by treating arbitrary raw OCR numbers as verified statistics.

Examples for future annotation include right-side S13 results, left-side basic-mode results, and normal left/right double results. Need tests for leading zeros, partially obscured digits, labels confused with numbers, unstable result animations, missing rows and conflicting players. `MAX COMBO` is not a total-judgment count, and a judgment total is not automatically a chart note count; no such scoring invariant was established here.

## Evidence and operational handoff

Useful local artifacts are ignored by Git and are not required to run the source code:

- `outputs/heldout-survey/`: whole-recording survey sheets, including plays missed by the original fixed-HUD detector.
- `outputs/mode-inspection/`: single/basic-mode gameplay frames.
- `outputs/heldout-results/`: result/summary samples, including left-side double badges.
- `outputs/missing-results/`: right S13/S19, left VERY HARD results, and an unobscured title after an overlay.
- `outputs/alternate-boundary-review/`: decoded single/basic-mode boundary samples with original timestamps.
- `outputs/title-regression-v4/`: original versus selectively processed title evidence.
- Final `evidence/segment-*/ocr.json` files under the two runs in [validation](validation.md): per-frame phase, eligibility, raw/focused OCR, source PTS and label evidence.

Use the original media plus `frames.json`/OCR metadata to reproduce a check; a contact-sheet cell is not an exact timestamp. Keyframe proposals can be seconds away from a decoded boundary. Preserve source PTS, distinguish local playback from YouTube time, and never derive an offset from duration metadata alone.

Direct mise-shim commands work in the configured project environment; no extra `zsh -c` is needed. Vision OCR may require host execution permission even when FFmpeg and offline unit tests work in the sandbox. Do not interpret that permission failure as unreadable media or bypass it. Keep OCR binary/module caches local. Keep prior output directories when retrying; they explain regressions and must not be silently overwritten. Run `just check`, and `just check-ocr` when changing OCR behavior. Record the host OS/Vision version when comparing measurements.
