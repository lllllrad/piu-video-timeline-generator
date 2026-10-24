import { readFileSync } from "node:fs";
import { createSegmentLabeler, parseTimeline, timestamp } from "../lib/timeline.ts";

const input = process.argv[2];
if (!input) throw new Error("analysis JSON path is required");
const timeline = parseTimeline(JSON.parse(readFileSync(input, "utf8")));

const segmentLabel = createSegmentLabeler(timeline);
const lines = ["00:00 auto-generated timeline started"];
for (const segment of timeline.segments) {
  lines.push(`${timestamp(segment.start_seconds)} ${segmentLabel(segment)} start`);
  lines.push(`${timestamp(segment.end_seconds)} ${segmentLabel(segment)} end`);
}
console.log(lines.join("\n"));
