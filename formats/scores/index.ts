import { readFileSync } from "node:fs";
import { field, createSegmentLabeler, onlyResultPlayer, parseTimeline, timestamp } from "../lib/timeline.ts";

const input = process.argv[2];
if (!input) throw new Error("analysis JSON path is required");
const timeline = parseTimeline(JSON.parse(readFileSync(input, "utf8")));

const segmentLabel = createSegmentLabeler(timeline);
for (const segment of timeline.segments) {
  const player = onlyResultPlayer(segment);
  const score = field<number>(player, "score");
  const suffix = score === undefined ? "" : ` — ${score.toLocaleString("en-US")}`;
  console.log(`${timestamp(segment.start_seconds)} ${segmentLabel(segment)}${suffix}`);
}
