#!/usr/bin/env -S deno run --allow-read --allow-write
/** Executable example: read analysis JSON, run arbitrary logic, write paste-ready text. */

import { label, parseTimeline, timestamp } from "./timeline_utils.ts";

const [input, output] = Deno.args;
if (!input || !output) throw new Error("usage: timeline.ts INPUT.json OUTPUT.txt");

const timeline = parseTimeline(JSON.parse(await Deno.readTextFile(input)));
const lines = ["00:00 auto-generated timeline started"];

for (const segment of timeline.segments) {
  // Add filtering, renaming, grouping, player selection, or any other logic here.
  lines.push(`${timestamp(segment.start_seconds)} ${label(segment)} start`);
  lines.push(`${timestamp(segment.end_seconds)} ${label(segment)} end`);
}

await Deno.writeTextFile(output, `${lines.join("\n")}\n`, { createNew: true });
