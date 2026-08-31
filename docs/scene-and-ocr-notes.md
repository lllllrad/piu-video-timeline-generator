# Scene, layout and OCR field notes

These notes record reusable observations from the Phoenix recordings described in [validation](validation.md). They are implementation guidance, not a universal PIU specification. Proposed layout changes belong in [layout and result design](layout-and-result-design.md).

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

The current implementation does not track this whole sequence. `piu_timeline.auto_timeline` detects HUD intervals and samples relative to their boundaries:

- Selection: start minus 8, 6, 4 and 3 seconds.
- Result: end plus 3, 5, 7, 8, 9, 10, 11 and 12 seconds.
- Summary fallback: end plus 12, 14 and 16 seconds, only when a song is known but its chart is unknown.

These offsets worked on the tested material; they are not game timing constants. A future scene tracker should locate stable screens instead of assuming these windows always contain the right scene. Do not sample into the next play and assign its result to the previous play.

`is_result_screen()` currently requires `SCORE` plus at least one of `PERFECT`, `MAX COMBO` or `KCAL` after text normalization. This prevents the observed failure-message/title error, but OCR can miss a marker and reject a genuine result. Selection sampling does not yet have an equivalent full scene gate.

## Player side and result layout

Player-dependent P1/P2 layouts require both sides to be supported. Directly observed: the chart badge, score/grade and judgment values can occupy the left or right part of the result screen while the title stays centered. Judgment labels may remain near the center while their associated values move to the active side. Do not mirror the entire screen or assume every field uses the same transform.

Keep three concepts separate: the image-side slot (`left`/`right`), the logical game player (`P1`/`P2`), and the person being analyzed. The current result model retains P1/P2 slots separately but does not follow a person's identity across scenes. Mirrored captures and unfamiliar layouts require renewed verification.

Current result parsing keeps recognized left/right slots separate. A single-player output selector resolves automatically only when one slot is confidently present. Simultaneous two-player screens, independent player failures and transitions between one/two players still need broader real-video validation.

For future score extraction, bind the chart, score, grade and judgments to the **same result slot and play interval**. Never combine a left-player chart with right-player judgment numbers. Double mode is a chart mode, not evidence that two players are present.

## Coordinate conventions and current regions

The default game rectangle is the top-left 1300x730 area of a 1920x1080 source. It excludes the camera below and chat/camera content to the right. `--game-roi x,y,width,height` overrides it in source pixels. Internal OCR boxes are normalized to the cropped game image, with origin at the top left. Focused OCR is mapped back into that space. Do not confuse source pixels, game-relative fractions and enlarged OCR-image coordinates.

The following are current implementation crops, not a calibrated layout schema. Each tuple is `(x, y, width, height)` relative to the game image; see `focused_lines()` in `src/piu_timeline/recognition.py`.

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

## Judgment counts

Optional result extraction reads `PERFECT`, `GREAT`, `GOOD`, `BAD`, `MISS`, `MAX COMBO` and `SCORE` into separate player slots. Each value needs corroborating stable frames; unreadable, conflicting or weak evidence remains unknown. Calories and grades are not implemented output fields.

Leading zeros, partially obscured digits, unstable animations, missing rows and genuine simultaneous-player results need continued validation. `MAX COMBO` is not a total-judgment count, and a judgment total is not automatically a chart note count.

## Evidence

Use the original media plus `frames.json` and OCR metadata to reproduce a check; a contact-sheet cell is not an exact timestamp. Keyframe proposals can be seconds away from a decoded boundary. Preserve source PTS, distinguish local playback from YouTube time, and never derive an offset from duration metadata alone. Keep prior output directories when comparing regressions, and record the host OS/Vision version when comparing OCR measurements.
