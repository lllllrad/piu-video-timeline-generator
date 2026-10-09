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

Each accepted play samples the gameplay HUD for its displayed `STAGE 01` through `STAGE 06` number. The value is stored per segment and may reset to 1 when another credit begins. It is not inferred from segment order or from an assumed number of stages. A combined play-result screen may follow the last stage, but is not required for stage numbering. The recognized stage number selects the matching ordinal row (`1ST` through `6TH`) to verify both song and chart, including correction of a transient selection-screen chart. The summary remains evidence rather than a separate timeline segment. Summary chart columns support both left and right slots, including different simultaneous charts. All readable ordinal rows are retained, and two agreeing summary frames can repair earlier numbered stages in the current credit. A stage reset or unknown/non-increasing stage stops backward association. A correction retains the previous labels and marks the play for review. Unresolved candidates are retained until credit reconciliation finishes, so a later summary can recover an earlier failed play. Only candidates still lacking both song and chart are then excluded. Explicit demo screens are excluded separately.

Song resolution precedes chart resolution. A fallback chart is accepted only from frames whose title matches the resolved song; the analyzer cannot combine one browsed song with another song's chart. Duplicate source timestamps cannot vote twice. A single high-confidence title no longer overrides missing corroboration.

## Player results

Each play may contain independent P1 and P2 result slots. A slot retains:

- logical player and image side;
- chart evidence;
- score, max combo and judgment counts;
- recognized, unknown or conflicting status per field;
- source frames and OCR agreement evidence.

Player identities live in `segment.players`, separately from `segment.results.players` statistics. Account labels must occupy the top name band, include a readable account discriminator, and agree across multiple frames. Names never establish judgment values or transfer them across sides. There is no mapping from account labels to real-world identities.

Never combine fields across slots. A single-player helper may resolve a player only when exactly one slot is confidently recognized. Double is a chart mode, not proof that two people are playing.

## Proposed game-panel localization

A future locator should use several stable Phoenix UI anchors across different scenes, fit a scale/translation transform, and validate persistence over time. Motion alone is insufficient because backgrounds, cameras and chat also move. Ambiguous localization should request an explicit crop rather than silently selecting a region.

Validation must include translated, resized, borderless and full-frame game panels as well as overlays and composition changes. Synthetic transforms supplement but do not replace real recordings.
