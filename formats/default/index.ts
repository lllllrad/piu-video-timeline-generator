import { readFileSync } from "node:fs";
import { hasDifferentPlayers, playerLabel, parseTimeline, timestamp } from "../lib/timeline.ts";

const input = process.argv[2];
if (!input) throw new Error("analysis JSON path is required");
const timeline = parseTimeline(JSON.parse(readFileSync(input, "utf8")));

const includeNames = hasDifferentPlayers(timeline);
const lines = ["00:00 auto-generated timeline started"];
for (const segment of timeline.segments) {
  lines.push(`${timestamp(segment.start_seconds)} ${playerLabel(segment, includeNames, true)} start`);
  lines.push(`${timestamp(segment.end_seconds)} ${playerLabel(segment, includeNames, true)} end`);
}
console.log(lines.join("\n"));
