# Custom output formats

A format is a TypeScript program, not a template language or configuration object. It reads one saved analysis file and prints text to stdout. Node.js 24 runs the `.ts` file directly, so no `npx`, `tsx`, package install or format-specific build step is involved.

## Create a format

Create `.local/formats/my-format/index.ts`:

```ts
import { readFileSync } from "node:fs";
import { label, parseTimeline, timestamp } from "../../../formats/lib/timeline.ts";

const timeline = parseTimeline(JSON.parse(readFileSync(process.argv[2], "utf8")));

for (const segment of timeline.segments) {
  console.log(`${timestamp(segment.start_seconds)} ${label(segment)}`);
}
```

Run it by name:

```sh
just auto VIDEO my-format
```

The result is printed and saved as `.local/data/<video-id>/output/my-format.txt`. Running the format again reuses analysis and replaces only that derived text file.

If `.local/formats/<name>/` exists, it owns that format name. A missing `index.ts` or a formatter error stops the command; the workflow does not silently fall back to a bundled format. A failed run also removes the previous derived text file so stale output cannot be mistaken for the new result.

## Shared utilities

[formats/lib/timeline.ts](../formats/lib/timeline.ts) defines the analysis types and small optional helpers:

- `parseTimeline(value)` validates untyped JSON and returns `TimelineDocument`.
- `TimelineSegment.stage` is the stage number (`1` through `6`) recognized from the HUD or uniquely matched to a corroborated numbered summary row, or `null`.
- `timestamp(seconds)` floors a playback time to `MM:SS` or `H:MM:SS`.
- `label(segment)` joins a song name and chart without stray punctuation. Half Double badges use `HD`, for example `HD17`; Single and Double retain `S` and `D`.
- `hasDifferentPlayers(document)` detects distinct corroborated accounts or simultaneous result slots.
- `playerLabel(segment, includeNames)` adds player names and, for simultaneous players, each slot's chart.
- `TimelineSegment.players` stores identity evidence separately from `results.players` score evidence.
- `onlyPlayer(segment)` returns the sole recognized player, if unambiguous.
- `field(player, name)` returns a recognized player field without converting missing data to zero.

Formats may ignore these helpers and implement any logic they need. [formats/scores/index.ts](../formats/scores/index.ts) demonstrates typed access to the recognized score.

## Input contract

The first argument is the absolute or project-resolved path to `analysis.json`. The program must:

- write only the formatted result to stdout;
- end stdout with a newline;
- send diagnostics to stderr;
- exit non-zero on failure.

Formatting does not receive the video and must not modify analysis or evidence files.

A play's `results.status` may be `not_displayed` with `reason: stage_break_screen` when repeated life-loss screens replace the score table. Such a result has no numeric players and is not an OCR failure. Missing visible fields retain their `unknown` or `conflict` evidence states.
