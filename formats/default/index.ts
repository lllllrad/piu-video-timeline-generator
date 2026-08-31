import { readFileSync } from "node:fs";
import { label, parseTimeline, timestamp } from "../lib/timeline.ts";

const input = process.argv[2];
if (!input) throw new Error("analysis JSON path is required");
const timeline = parseTimeline(JSON.parse(readFileSync(input, "utf8")));

const lines = ["00:00 auto-generated timeline started"];
for (const segment of timeline.segments) {
  lines.push(`${timestamp(segment.start_seconds)} ${label(segment)} start`);
  lines.push(`${timestamp(segment.end_seconds)} ${label(segment)} end`);
}
console.log(lines.join("\n"));
