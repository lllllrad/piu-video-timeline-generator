import { readFileSync } from "node:fs";
import { field, label, onlyPlayer, parseTimeline, timestamp } from "../lib/timeline.ts";

const input = process.argv[2];
if (!input) throw new Error("analysis JSON path is required");
const timeline = parseTimeline(JSON.parse(readFileSync(input, "utf8")));

for (const segment of timeline.segments) {
  const player = onlyPlayer(segment);
  const score = field<number>(player, "score");
  const suffix = score === undefined ? "" : ` — ${score.toLocaleString("en-US")}`;
  console.log(`${timestamp(segment.start_seconds)} ${label(segment)}${suffix}`);
}
