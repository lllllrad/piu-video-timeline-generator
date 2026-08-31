# Timeline presentation and player results

`just analyze` stores reusable timing, song, chart and evidence data in `analysis.json`. Presentation is a separate local step and does not need video decoding, OCR or network access.

## Executable TypeScript formatter

[templates/timeline.ts](../templates/timeline.ts) is a normal Deno program, not a configuration object. It receives an input JSON path and output text path, reads `segments`, and may apply arbitrary filtering, grouping, renaming, player selection or other TypeScript logic.

```sh
just format .local/outputs/analysis/analysis.json .local/outputs/timeline.txt

# Use a copied or custom program instead.
just format analysis.json timeline.txt .local/my-timeline.ts
```

[templates/timeline_utils.ts](../templates/timeline_utils.ts) provides:

- `TimelineDocument` and `TimelineSegment` interfaces;
- runtime validation for untyped JSON input;
- whole-second `timestamp()` formatting;
- `label()` construction for song and chart text.

Custom programs can import any, all or none of these helpers. The example reads JSON directly and writes with `createNew: true`, so it will not silently overwrite an earlier timeline.

Its default output is ready to paste:

```text
00:00 auto-generated timeline started
01:23 곡명 D20 start
03:45 곡명 D20 end
```

## Saved player results

Use `just analyze VIDEO OUTPUT --judgments` to extract player-separated counts during analysis, or `just results OLD_ANALYSIS NEW_OUTPUT` to add them later from retained result-frame evidence. Counts remain under `segments[].results.players.p1` and `p2`; absent, ambiguous and conflicting values are never converted to zero or borrowed from the other player.

The older `just render` conditional judgment-report renderer remains available. Its optional `--template` argument accepts JSON data only. For arbitrary output logic, use the TypeScript formatter instead.

Generated analysis, reports and media belong under `.local/` and remain outside Git. Original media and previous outputs are never overwritten.
