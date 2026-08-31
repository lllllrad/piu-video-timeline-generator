# Player judgments and conditional output

Implemented commands: `just analyze`, `just results`, `just render`, and the combined `just auto` convenience workflow. Templates use **TOML or JSON**, parsed with the pinned Python's standard library; no new package install is needed. The YAML game-layout/CV design remains separate and is not a supported configuration file yet.

## Normal workflow: one player, either side

```sh
# Analysis does not require a timeline, template, or P1/P2 output choice.
just analyze '/path/to/video.mkv' .local/outputs/analysis --judgments

# After inspecting the evidence, choose presentation independently.
just render .local/outputs/analysis/analysis.json .local/outputs/report --template templates/judgments.toml

# Optional combined workflow:
# The template requests player fields, so judgment OCR turns on automatically.
just auto '/path/to/video.mkv' .local/outputs/run --template templates/judgments.toml

# Or request the default count report without writing a template.
just auto '/path/to/video.mkv' .local/outputs/run-with-counts --judgments

# A quick one-off detail template also automatically enables count extraction.
just auto '/path/to/video.mkv' .local/outputs/quick --detail 'P {player.perfect} / G {player.great} / Miss {player.miss}'
```

`--player single` is the default. For each play, `{player.perfect}`, `{player.great}`, etc. refer to the **only confidently detected player**, whether that player is P1 or P2. The selection may change sides between plays; it does not track a person's identity. `{perfect}`, `{great}`, etc. are shorthand aliases for the selected player.

If both slots are detected, or another slot has uncertain presence, `single` does not guess. Selected-player fields become unknown, conditions depending on them do not match, and `rendered.json` records warnings. A failed play without a usable result remains in the timeline with unknown counts, never zero counts. This preserves the timeline instead of silently dropping hard-to-read plays.

`analyze` accepts no presentation arguments; only `--judgments` controls optional count extraction, independently of future output. Analysis retains all detected player slots. Without that flag it produces song/chart/timing evidence, to which counts can be added later. It records gameplay intervals and sampled scene evidence, not an exhaustive full-video scene sequence.

For the combined `auto` command, no template and no judgment flag preserves the song/chart-only workflow. `--no-judgments` explicitly forbids extraction; a template or player selector that requires results then fails before media downloading/processing. Invalid placeholders/configuration also fail early. Template-driven OCR inference belongs only to this convenience wrapper, not the analysis function.

## Existing runs: do not analyze the whole video again

```sh
# Add counts using the retained game-only result frames; no original video needed.
just results .local/outputs/old-run/timeline.json .local/outputs/with-counts

# Inspect a few one-based segment numbers first. The output contains only these plays.
just results .local/outputs/old-run/timeline.json .local/outputs/sample-counts --segment 18 --segment 25

# Change presentation without OCR, FFmpeg, Vision or network access.
just render .local/outputs/with-counts/analysis.json .local/outputs/new-format \
  --detail 'Perfect {player.perfect}, Great {player.great}, Miss {player.miss}'
```

Run these from the project root; older evidence paths are project-relative. Keep the earlier `evidence/` images and `ocr.json` files for `results`. Missing frames fail preflight with instructions to restore them or rerun `auto --judgments`. `render` needs only the enriched JSON and template, so it also works on hosts without macOS Vision. Trying to render player fields from old JSON without results gives an actionable `just results` error rather than pretending every count is unknown.

`results` accepts both new `analysis.json` and older automatic `timeline.json`. It writes enriched `analysis.json` only by default. To also render immediately, add `--render`; explicit presentation arguments such as `--template` imply `--render` for compatibility. Selecting `--segment` produces analysis containing only those plays; it does not modify the original document.

All output directories must be new. Commands never overwrite source JSON, source media, earlier frames or an existing report. Failed analysis/enrichment can retain partial evidence/checkpoints but no completed `analysis.json`. Completed analysis is saved before optional rendering, so a presentation failure never discards successful OCR. A compatibility `timeline.json` is written only after optional rendering succeeds. Retry rendering from `analysis.json` into a fresh directory without repeating OCR.

## Player selection and placeholders

Normal unmirrored game coordinates use P1=left and P2=right. Mirrored/rotated/unlocalized game screens are not automatically corrected by this feature. The game crop is still supplied by the existing default or `--game-roi`; this implementation does not yet include CV game-panel localization.

| Option | Selected-player aliases | Missing/ambiguous behavior |
| --- | --- | --- |
| `--player single` (default) | The only recognized slot, on either side | Unknown aliases if zero, two, or uncertain slots |
| `--player p1` | Left/P1 only | Never borrow P2's chart or statistics |
| `--player p2` | Right/P2 only | Never borrow P1's chart or statistics |
| `--player all` | One output entry per detected slot | Appends `[P1]`/`[P2]`; an unavailable result retains one unknown entry |

Supported selected-player fields: `perfect`, `great`, `good`, `bad`, `miss`, `max_combo`, `score`, `chart`, `player_id`, `side`. Use `{player.FIELD}`, `{p1.FIELD}` or `{p2.FIELD}`. Explicit `{p1.*}`/`{p2.*}` namespaces do not change with `--player`. This allows a combined detail such as `P1 {p1.perfect} / P2 {p2.perfect}`. Unknown fields print `?` when the block's missing policy allows display.

Global fields are `{timestamp}`, `{song}`, `{chart}`, `{chart_suffix}`, `{player_id}`, `{side}` and the short numeric aliases. `{chart_suffix}` includes the brackets and leading space only when a chart is known. For player-aware output, `{chart}` comes from the selected slot. For an old song-only timeline or a failed play with no player result, the default single-player title can retain the segment's known chart; `{player.chart}` remains unknown. Grade, calories and derived clear classifications are not implemented fields.

`all` can create duplicate timestamps for the two players. It is a player report, not a guarantee of valid YouTube chapter formatting. Choose `single`, P1 or P2 for a single timestamp-list entry per play. Timestamps remain local playback times; rendering does not infer YouTube alignment.

## Configuration and conditional rules

Start with [templates/judgments.toml](../templates/judgments.toml). CLI `--player`, `--title` and repeated `--detail` values override the corresponding base configuration. Rules are then evaluated in order and the first matching rule wins. A rule can replace the title, details, or both; omitted properties inherit the base configuration.

```toml
version = 1
player = "single"
title = "{timestamp} {song}{chart_suffix}"

[[details]]
text = "P {player.perfect} / G {player.great} / Miss {player.miss}"
missing = "show"

[[details]]
text = "Score {player.score}"
missing = "omit"
when = { field = "player.score", op = "recognized" }

[[rules]]
title = "{timestamp} {song}{chart_suffix} — Miss {player.miss}"
when = { field = "player.miss", op = "gt", value = 0 }
```

Numeric operators: `eq`, `ne`, `lt`, `le`, `gt`, `ge`, with non-negative integer comparison values. Text fields support `eq`/`ne`. `recognized` takes no value. Use `when.all = [...]` or `when.any = [...]` for one-level groups. Unknown/conflicting values never satisfy comparisons, including `ne`; recognized zero is a real value, not missing.

Details can have their own `when`, a `requires = [...]` list and `missing = "omit" | "show" | "error"`. Placeholders automatically count as required fields. `omit` skips the unavailable block, `show` prints `?`, and `error` stops rendering with the segment number and missing fields. Missing title fields remain visible and generate warnings. No missing value is silently converted to zero. The bundled all-perfect rule checks every non-perfect judgment count plus a positive PERFECT count; its suffix is a user-defined description, not an official game grade.

Only whitelisted plain placeholders are allowed. There is no expression evaluation, object traversal, function execution or format-specifier language. `{{` and `}}` produce literal braces. Unknown keys, duplicate TOML/JSON keys and invalid rule types are errors. Configuration is limited to 64 KiB, templates to 4096 characters, and rule/detail/group counts to 50. Newlines and control characters are flattened so OCR text cannot inject extra timestamp rows.

## Outputs and data quality

- `analysis.json`: structured gameplay timing/song evidence plus `segments[].results` when counts are extracted. `artifact_type: video_analysis`, `timestamp_basis: local_playback`, and `analysis_options.judgments` describe the analysis independently of presentation. `results.players.p1` / `p2` keep counts separate, with per-field `value`, `status`, agreement and confidence evidence. `fields` is authoritative; flattened values are convenience copies. No selected output player, title or template is stored in analysis. Rendering alone does not rewrite this file.
- `timeline.json`: compatibility copy of analysis (plus the legacy `text_timestamp_basis` field), emitted only by `auto` or `results` with optional rendering. Existing automatic JSON remains accepted by `results`, `render`, and evaluation.
- `timeline.txt`: title lines only.
- `details.txt`: each title and its optional detail lines, separated by blank lines.
- `rendered.json`: resolved template configuration, selected slot, matched rule, review flag and warnings for each rendered entry.
- Result evidence directory: game-relative numeric/chart crops and per-frame OCR with original source PTS. Existing evidence is not overwritten.

At least two distinct sampled frame timestamps must corroborate a slot/field. A count needs a strict majority of readable values and mean OCR confidence at least 0.7. Missing, low-confidence or tied values remain unknown/conflict. Background digits alone do not establish a player: a chart badge or a score panel corroborated by judgment rows is required. The result scene gate excludes known failure/summary screens. Repeated OCR agreement can still be wrong; inspect evidence for publication-sensitive results.

This uses game-relative regions for the tested result layout, not arbitrary score-table understanding. Actual left/right single-player screens and a synthetic simultaneous two-player OCR fixture are tested. Genuine simultaneous two-player recordings, independent player failures and nonstandard crops still need broader validation. See [validation](validation.md) for measured sample results and unknowns.
