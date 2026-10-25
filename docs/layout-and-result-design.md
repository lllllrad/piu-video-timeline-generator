# Layout and result design

The source may contain cameras, chat or overlays around the game. `--game-roi` is an explicit source-pixel rectangle; automatic discovery currently finds HUD positions only inside that game crop. General game-panel localization remains future work.

## Coordinate spaces

- Source rectangles use encoded-frame pixels.
- Recognition regions use normalized coordinates inside the game crop.
- Saved evidence records the resolved crop, source timestamp and local playback timestamp.

Moving a crop constant alone is insufficient when a parser also constrains field position. Acquisition regions and positional validation must change together.

## Scene model

The useful sequence is selection, song introduction, gameplay, transition and per-song result. Failed plays may skip a usable per-song result and reach a multi-song summary instead. The analyzer detects gameplay HUD intervals, classifies nearby sampled screens, and resolves evidence after acquisition. It is not a continuous scene tracker. Summary detection takes precedence over per-song result markers, and unknown screens cannot supply titles.

The black transition and the score screen are evidence around a play, not part of its detected gameplay interval. Publication boundaries require separate audio/video review.

Each accepted play samples the gameplay HUD for its displayed `STAGE 01` through `STAGE 06` number. The value is stored per segment and may reset to 1 when another credit begins. A missing HUD number can also be recovered from a unique title match (including bounded OCR spelling variants) against a numbered summary row confirmed in two distinct frames of the same credit. Repeated titles/rows remain ambiguous. Stage numbers are not inferred from segment order or from an assumed number of stages. A combined play-result screen may follow the last stage, but is not required for stage numbering. The recognized stage number selects the matching ordinal row (`1ST` through `6TH`) to verify both song and chart, including correction of a transient selection-screen chart. The summary remains evidence rather than a separate timeline segment. Summary chart columns support both left and right slots, including different simultaneous charts. All readable ordinal rows are retained, and two agreeing summary frames can repair earlier numbered stages in the current credit. A stage reset or unknown/non-increasing stage stops backward association. A correction retains the previous labels and marks the play for review. Unresolved candidates are retained until credit reconciliation finishes, so a later summary can recover an earlier failed play. Only candidates still lacking both song and chart are then excluded. Explicit demo screens are excluded separately.

Song resolution precedes chart resolution. A fallback chart is accepted only from frames whose title matches the resolved song; the analyzer cannot combine one browsed song with another song's chart. Duplicate source timestamps cannot vote twice. A single high-confidence title no longer overrides missing corroboration.

## Player results

Each play may contain independent P1 and P2 result slots. A slot retains:

- logical player and image side;
- chart evidence;
- score, max combo and judgment counts;
- recognized, unknown or conflicting status per field;
- source frames and OCR agreement evidence.

Player identities live in `segment.players`, separately from `segment.results.players` statistics. Account labels must occupy a dedicated top name band and agree across distinct source frames. Enlarged crops read the nickname independently of title/score recognition. Full-screen guesses require a readable account discriminator; dedicated crops may retain a repeated nickname when the discriminator is unreadable. A bare nickname also requires a visible rank/header on the same side, so background-video captions on an empty player side cannot become identities. Repeated dedicated-strip readings take precedence over full-screen guesses of tiny account glyphs, with the alternatives retained. Tiny `#` glyphs may appear as `+` or `*` in focused OCR; conflicting digits are retained as alternatives instead of inferred. Names never establish judgment values or transfer them across sides. There is no mapping from account labels to real-world identities.

Never combine fields across slots. A single-player helper may resolve a player only when exactly one slot is confidently recognized. Double is a chart mode, not proof that two people are playing.

## Proposed game-panel localization

A future locator should use several stable Phoenix UI anchors across different scenes, fit a scale/translation transform, and validate persistence over time. Motion alone is insufficient because backgrounds, cameras and chat also move. Ambiguous localization should request an explicit crop rather than silently selecting a region.

Validation must include translated, resized, borderless and full-frame game panels as well as overlays and composition changes. Synthetic transforms supplement but do not replace real recordings.

## Credit sequence and sampling

A credit starts with coin/start interaction and may include account and Basic/Premium mode selection. Selection, gameplay and a successful score result or failure screen then repeat one to six times, followed by a combined play result. Not every recording shows every step; sampling must preserve uncertainty about missing steps.

Detected HUD intervals anchor this sequence. Label samples stay in neighboring gameplay gaps. Early post-game samples cover brief results; a singleton result/summary receives nearby samples to corroborate a short screen. Numbered titles remain usable even when chart badges are unreadable, and raw badge glyphs supplement focused crops when columns move. Sparse pre-game samples cover selection. A bounded gap scan at two downscaled grayscale frames per second nominates screen-change representatives before OCR. Sparse guard samples protect against missed changes; unresolved labels, absent results, or an empty transition plan activate fixed-offset coverage. Unresolved identities add bounded pre-game probes without making dense label OCR unconditional. Scan plans and OCR observations are retained for reuse. Dedicated numeric result OCR is limited to six source frames spread across the observed result duration. This limits metadata OCR independently of decoded frame count. Future note tracking must read gameplay frames and original timestamps through the visual-analysis path without invoking metadata OCR on each frame.

A combined result, observed start/mode screen, known stage reset, or six-play limit closes a credit. Missing stage text can preserve continuity when an intervening result/failure is observed; otherwise association stops. Names may be corroborated across a credit on the same player side. Local account conflicts or different recognized accounts prevent propagation. A previous result/summary sampled before the next gameplay cannot vote for the next player's name. Names are never carried across an observed credit boundary.

## Stylized chart badge numerals

The small `SINGLE`/`DOUBLE` caption and the large numeral are different text regions. A full-badge detector can read the caption while missing the numeral or reading only its last digit. Result and summary badge columns therefore also use observed circular outlines to nominate complete badge crops. Summary circles must be near an observed ordinal row; ambiguous row assignments abstain. A readable mode caption anchors the numeric strip below it. The Linux recognizer reads that known strip directly, bypassing text detection, in both original pixels and a white-text-isolated variant. Both variants must agree. Their agreement is **one original-frame observation**, never two confirmation votes. Derived crops depend on source image content and numeric crop geometry.

A validated regional reading takes precedence over incomplete mode/numeral hypotheses inside the same badge when parsing. Raw hypotheses remain in the saved evidence. Other player slots, result counts and neighboring summary rows are independent. Confirmation still requires at least two distinct original source timestamps and a strict majority. Summary recovery also requires a matching title and an established participant slot; a rival badge cannot supply a player's chart.

`just auto` performs a bounded recovery pass for missing chart fields using retained metadata images, with at most six result frames and six summary frames per unresolved play. It caches observations under `analysis/evidence/chart-badge-recovery.json`, keyed by image content, retained glyphs and the OCR/badge contracts. It does not decode gameplay frames or rerun judgment-count OCR. Source media is untouched. Missing or ambiguous evidence remains unresolved.

Basic-mode `VERY HARD 12` remains the displayed label. When matching-title summary badges independently establish `S12`, the segment stores a separate `chart_identity` with its original-frame evidence. Chart registration accepts this corroborated identity without rewriting the displayed label or guessing Single from the basic-mode wording. Play refits propagate changed identity metadata from the saved timeline while reusing native observations.
