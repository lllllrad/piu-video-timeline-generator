# Game-screen localization, result statistics and output templates

This document separates implemented data-model decisions from proposed game-screen localization work. Player judgments and executable TypeScript presentation are implemented. CV localization and YAML game-layout configuration are proposals; their examples are not accepted configuration. See [timeline presentation](result-templates.md) for current usage and [field notes](scene-and-ocr-notes.md) for observed layouts.

## Direction and implementation order

Design assumption clarified by the user: this is one game, not a catalog of game variants or known stream layouts. The unknown is the game screen's location and size within the recording. Selection, gameplay, result and P1/P2 arrangements are states of that same game, not separate game variants.

Separate game-screen localization, game-relative UI geometry, scene/player association, result recognition and presentation. Configuration should describe how to recognize the game's UI and allow overrides, not require a predefined layout for each streamer or contain expected song names/scores.

Implemented separation: `just analyze` saves structured `analysis.json` without requiring a timeline, template or output player selection. `just results` enriches saved frame evidence without rendering by default. `just render` independently applies presentation; `just auto` remains the optional combined convenience workflow. Analysis completion is persisted before presentation so template errors do not discard completed OCR. The current analysis schema retains gameplay `segments` and sampled scene evidence; exhaustive scene segmentation is not implied by this separation.

1. Prototype CV localization of the game rectangle without a known stream layout. Normalize that rectangle into game coordinates and check that the existing recognition still works.
2. Extract game-relative geometry and parser constraints into versioned YAML configuration, with explicit ROI overrides for detection failures. Keep the 45-play baseline as a regression check.
3. Add per-scene/per-player result slots, optional judgment extraction and title/detail templates. Re-rendering should not require downloading or OCRing again.
4. Evaluate localization on unseen stream compositions and track changes over time. Save detected geometry as evidence or an editable override, not as a prerequisite profile catalog.

Start with classical CV and the game's stable UI elements; training a general detector is not a prerequisite. Coarse localization may already be sufficient if a subsequent alignment step places small OCR regions correctly. This feasibility hypothesis still needs a prototype and localization measurements. Numeric judgment extraction also requires separate real annotations.

## Layout configuration

Use YAML if it improves editing, with a strict schema and safe data-only loading. It introduces a parser dependency that should be pinned in the project environment. No executable tags, shell commands, arbitrary Python expressions or dynamic imports. Reject unknown keys, duplicate keys, unsupported versions, non-finite values and invalid/out-of-bounds rectangles. Apply resource limits to configuration size and parser features.

Use named coordinate spaces: source pixels for the detected game panel and normalized game coordinates for scene regions. Save source size, resolved pixel rectangles and the source-to-game transform with every run. Ordinary scale/translation is the initial target. Letterboxing, non-uniform stretching, rotation, mirroring and perspective must be detected or explicitly handled, not silently assumed away. Validation must include a different game-panel size and offset, not just a renamed copy of today's constants.

Illustrative **partial** game configuration, not a known stream-layout profile:

```yaml
schema_version: 1
id: piu-game-ui
source:
  game_rect: auto
  aspect_ratio_hint: [16, 9]  # Soft candidate prior, not a hard rejection rule.
  override_rect: null        # Optional source-pixel [x, y, width, height].
scenes:
  gameplay:
    hud_search_band: [0.0, 0.0, 1.0, 0.12]
    anchors: [STAGE]
  result:
    title_rect: [0.20, 0.15, 0.60, 0.07]
    title_center_y: [0.13, 0.23]
    required_markers:
      all: [SCORE]
      any: [PERFECT, MAX_COMBO, KCAL]
    slots:
      left:
        chart_rect: [0.26, 0.25, 0.15, 0.14]
        player_id: null  # Set P1/P2 only after verifying the mapping.
      right:
        chart_rect: [0.59, 0.25, 0.15, 0.14]
        player_id: null
```

A complete configuration also needs selection and summary regions, parser constraints, title-language/preprocessing policies, result-statistics label/value associations and scene/player-specific arrangements. Numeric-stat rectangles are deliberately not invented here; annotate them from the inspected left/right results. Keep decoding cadence and boundary thresholds in a separate analysis section, and presentation templates outside the layout geometry.

An explicit ROI override should take precedence over detection. Resolve precedence deterministically, save the resolved configuration plus a content hash/schema version, and never modify user configuration while processing media. Automatically discovered positions are run artifacts or proposed exported overrides, not hidden edits. Uncertain game-screen localization must be visible in the JSON and review flags.

## Player and result data model

Represent a play interval with one or more result slots rather than a single flattened score. Each slot should contain:

- Slot side, nullable logical player ID, chart mode/level and their evidence.
- Nullable score, grade, `perfect`, `great`, `good`, `bad`, `miss`, `max_combo` and optionally calories.
- Per-field status (`recognized`, `unknown`, `conflict`, `not_applicable`), raw text, source-frame PTS, image/ROI reference and confidence/agreement evidence.
- The result scene interval and its association with the gameplay segment. A selected target slot/player is an explicit output policy, not whichever side produced the largest OCR score.

Keep the displayed chart label as well as any parsed mode/level so basic-mode labels are not lost. Preserve existing top-level song/chart compatibility only when the selected slot is unambiguous; version any breaking JSON change. Two players on the same chart still require separate statistics. A missing result for one slot must not borrow the other slot's values.

## Optional judgment recognition

Enable numeric result OCR only when requested, or when required by selected rendering fields/rules under an explicit automatic-extraction option. Default operation should not pay the full recognition cost when statistics are unused. If extraction is disabled but a template requires statistics, report that clearly rather than quietly generating blanks or zeros.

Suggested procedure:

1. Locate a per-song result within the associated scene sequence and identify its active result slot(s).
2. Find judgment-label anchors and pair each with a value in that slot's declared region. Read numeric crops separately from title/grade text.
3. Sample multiple stable result frames; avoid overlays and any intermediate animation values. Track the same field in the same slot across frames.
4. Parse strict non-negative integers while preserving raw leading zeros and OCR alternatives. Do not silently substitute O/0 or I/1 without corroborating image evidence.
5. Keep conflicts/missing values explicit and flag review. Validate any arithmetic consistency rule separately for each supported game/mode; do not assume score formulas or note-count invariants.

Store unknown counts as `null`, never zero. Count-derived classifications require all their inputs to be known. In particular, zero MISS alone does not establish that every judgment was PERFECT, and a summary chart badge supplies no missing judgment counts. Treat official clear/grade terminology as a separately verified rule or directly recognized label, not an improvised consequence of a few counts.

## Title and detail templates

Keep the structured analysis authoritative. Rendering consumes it and cannot change source timestamps, recognition confidence or raw counts. Support a one-line chapter/title and optional detail text so YouTube timestamp lists can remain simple while Markdown/JSON reports include statistics. Details are not automatically part of a YouTube chapter title.

Illustrative rendering configuration (proposed syntax):

```yaml
render:
  target_slot: auto  # Only resolve automatically when unambiguous.
  title: "{timestamp} {song} [{chart}]"
  details:
    - requires: [judgments.perfect, judgments.great,
                 judgments.good, judgments.bad, judgments.miss]
      missing: omit
      text: "P {judgments.perfect} / G {judgments.great} / Good {judgments.good} / Bad {judgments.bad} / Miss {judgments.miss}"
  title_rules:  # First match wins; default title is the fallback.
    - when:
        all:
          - {field: judgments.perfect, op: gt, value: 0}
          - {field: judgments.great, op: eq, value: 0}
          - {field: judgments.good, op: eq, value: 0}
          - {field: judgments.bad, op: eq, value: 0}
          - {field: judgments.miss, op: eq, value: 0}
      title: "{timestamp} {song} [{chart}] — All judgments perfect"
```

These example rules require recognized values: `null`, conflict, not-applicable or insufficient evidence does not satisfy a numeric predicate. The example suffix is a user-defined description, not a claim about the game's official grade. Add an explicit `exists`/`recognized` condition and a conservative review policy in the real schema; do not rely on truthiness, which confuses zero with missing.

Allow a small set of typed field comparisons and formatting operations; no `eval`, arbitrary attribute traversal or function execution. Validate placeholders before decoding a video. Escape or normalize OCR newlines/control characters so a title cannot create fake timestamp rows. Provide intentional policies for unknown songs/charts, missing detail blocks and a selected player that is absent. Preserve the current default output when no custom template is supplied.

## What can be recognized automatically?

There are distinct levels of automation:

| Capability | Current state / proposed approach | Failure behavior |
| --- | --- | --- |
| Additional STAGE positions inside a known game crop | Already implemented with sparse OCR and per-position HUD scans | Missing/unsupported initial HUD is an error; short/new skins can be missed. |
| Left/right active result slot | Implemented: chart badge or score panel corroborated by judgment rows over multiple frames; unmirrored P1=left/P2=right. No person tracking. | Return uncertain slots; never choose just by the largest number. |
| PERFECT/GREAT/etc. values | Implemented as optional game-relative numeric OCR with per-player, multi-frame evidence; see the usage guide. | Unknown/conflict fields, optional details omitted or flagged according to policy. |
| Game-panel rectangle in an unknown stream composition | Proposed: CV candidate generation plus stable game-UI anchors, fit scale/translation, then validate across time. No known stream layout is required. | Request a crop override when ambiguous; do not treat chat, overlays or replay windows as the primary game. |

### CV localization without known stream layouts

1. Sample frames across the recording, including selection/result scenes when available. Use edge/line structure, plausible rectangular regions and aspect ratio as inexpensive candidate proposals. Include borderless/full-frame candidates; a clearly visible monitor outline is not required.
2. Search at multiple scales for stable game UI elements such as the STAGE badge, receptor/gauge shapes, title bars and result-panel structure. These are references for the same game's UI, not templates of each stream composition. Optional sparse OCR can confirm anchors, but full-frame OCR on every frame is unnecessary.
3. Fit a candidate game-coordinate transform from several spatially separated anchors. One small STAGE patch does not determine the whole game rectangle reliably. Repeated score/judgment structure or other scene anchors should corroborate the extent. If borders are absent, anchor geometry can propose the rectangle directly.
4. Score geometric agreement and persistence across frames/scenes. Prefer a candidate that consistently explains the game's UI rather than whichever rectangle has the most motion: background videos and cameras also move, and chat can contain game-related words.
5. Refine the crop/alignment, normalize to game coordinates, and run the existing game-relative detector/OCR. Measure both rectangle accuracy and downstream title/chart/statistics accuracy: a roughly correct crop can still shift a small numeric ROI out of place.
6. Cache the transform for a stable stream composition, re-check on evidence of a composition change, and re-detect when it no longer fits. Emit a confidence-marked ROI preview and allow a manual override. Multiple real game feeds require explicit target selection if their evidence is equally plausible.

The changing background video is not a useful fixed appearance template for the entire game screen. The stable UI and its relative geometry are the stronger signals. Camera-only perspective views can be a later extension; they should not make ordinary embedded digital game-screen localization depend on a general scene-understanding model.

## Acceptance checks before shipping

- Automatic localization reproduces the 45-play baseline without a supplied stream ROI. Test translated/resized panels, full-frame captures and borderless embeds without per-stream configurations. Invalid YAML/overrides fail before output creation.
- Directly annotate numeric judgment values on left/right, single/double/basic, overlay and failure examples. Include genuine two-player examples and report unsupported cases rather than borrowing another player's result.
- Measure per-field exact count accuracy, player attribution, unknown/conflict rates and wrong-but-accepted values separately from song/chart accuracy. The existing evaluator does not yet measure statistics.
- Test templates with known zero, unknown, conflicts, absent players, empty details, illegal fields, embedded newlines and multiple matching rules. Verify re-rendering from JSON needs no media/network access.
- Evaluate game-rectangle localization on unseen stream compositions, including no-game scenes, overlays, letterboxing, composition changes and competing game feeds. Measure rectangle overlap/edge errors, downstream OCR accuracy, abstentions and false selections. Synthetic transformations supplement, but do not replace, real recordings.
- Retain source-time preservation, offline local inputs, comment separation, evidence storage and safe non-overwriting outputs.
