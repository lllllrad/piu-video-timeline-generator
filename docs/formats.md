# Custom output formats

A format is a TypeScript program, not a template language or configuration object. It reads one saved analysis file and prints text to stdout. Node.js 24 runs the `.ts` file directly, so no `npx`, `tsx`, package install or format-specific build step is involved.

## Create a format

Create `.local/formats/my-format/index.ts`:

```ts
import { readFileSync } from "node:fs";
import { createSegmentLabeler, parseTimeline, timestamp } from "../../../formats/lib/timeline.ts";

const timeline = parseTimeline(JSON.parse(readFileSync(process.argv[2], "utf8")));
const segmentLabel = createSegmentLabeler(timeline);

for (const segment of timeline.segments) {
  console.log(`${timestamp(segment.start_seconds)} ${segmentLabel(segment)}`);
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
- `songLabel(segment)` joins a song name and chart without stray punctuation. Half Double badges use `HD`, for example `HD17`; Single and Double retain `S` and `D`.
- `hasMultiplePlayers(document)` detects distinct recognized accounts or simultaneous participant slots. A missing discriminator does not turn the same nickname into a second account; two different recognized discriminators still distinguish accounts.
- `playerNames(segment, { accountDiscriminators: false })` returns only player names, with P1/P2 markers for simultaneous players. It never includes the song or chart.
- `createSegmentLabeler(document, options)` returns a function that formats a song and chart, automatically adding names when the recording has multiple players. Simultaneous charts stay associated with their P1/P2 slots.
- `TimelineSegment.players` stores identity evidence separately from `results.players` score evidence.
- `onlyResultPlayer(segment)` returns the sole recognized result slot, if unambiguous; it does not select from identity-only participants.
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

Both bundled formats use `createSegmentLabeler(timeline)` with the same defaults: song and chart always appear, one account's name stays hidden, and multiple players use nicknames without the trailing `#dddd` discriminator. Full identities remain in analysis for account distinction. Identity and result slots are considered together; uncertain identities do not establish another participant. Rival comparison slots are excluded from `players` and `results.players`, with header evidence retained under `excluded_slots`.

Control name presentation separately from song information:

```ts
const segmentLabel = createSegmentLabeler(timeline, {
  playerNames: "never", // "auto" (default), "always", or "never"
  accountDiscriminators: false, // true displays full account identities
});
```

With simultaneous players, hiding names retains each slot's chart, for example `Song [P1: S18 / P2: D20]`. For a simple song/chart string independent of participants, use `songLabel(segment)`. To print only names, use `playerNames(segment)`.
