# Layout and result design

The source may contain cameras, chat or overlays around the game. `--game-roi` is an explicit source-pixel rectangle; automatic discovery currently finds HUD positions only inside that game crop. General game-panel localization remains future work.

## Coordinate spaces

- Source rectangles use encoded-frame pixels.
- Recognition regions use normalized coordinates inside the game crop.
- Saved evidence records the resolved crop, source timestamp and local playback timestamp.

Moving a crop constant alone is insufficient when a parser also constrains field position. Acquisition regions and positional validation must change together.

## Scene model

The useful sequence is selection, song introduction, gameplay, transition and per-song result. Failed plays may skip a usable per-song result and reach a multi-song summary instead. The analyzer detects gameplay HUD intervals and samples nearby selection, result and summary screens; it is not an exhaustive scene classifier.

The black transition and the score screen are evidence around a play, not part of its detected gameplay interval. Publication boundaries require separate audio/video review.

Each accepted play samples the gameplay HUD for its displayed `STAGE 01` through `STAGE 06` number. The value is stored per segment and may reset to 1 when another credit begins. It is not inferred from segment order or from an assumed number of stages. A combined play-result screen may follow the last stage, but is not required for stage numbering. When several summary rows share a chart, the recognized stage number may select the matching ordinal row (`1ST` through `6TH`) to recover the song title; the summary remains evidence for that song rather than a separate timeline segment.

## Player results

Each play may contain independent P1 and P2 result slots. A slot retains:

- logical player and image side;
- chart evidence;
- score, max combo and judgment counts;
- recognized, unknown or conflicting status per field;
- source frames and OCR agreement evidence.

Never combine fields across slots. A single-player helper may resolve a player only when exactly one slot is confidently recognized. Double is a chart mode, not proof that two people are playing.

## Proposed game-panel localization

A future locator should use several stable Phoenix UI anchors across different scenes, fit a scale/translation transform, and validate persistence over time. Motion alone is insufficient because backgrounds, cameras and chat also move. Ambiguous localization should request an explicit crop rather than silently selecting a region.

Validation must include translated, resized, borderless and full-frame game panels as well as overlays and composition changes. Synthetic transforms supplement but do not replace real recordings.
