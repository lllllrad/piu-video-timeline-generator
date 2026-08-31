/** Types and small helpers for executable timeline formatters. */

export interface TimelineSegment {
  start_seconds: number;
  end_seconds: number;
  song: string | null;
  chart: string | null;
  [key: string]: unknown;
}

export interface TimelineDocument {
  segments: TimelineSegment[];
  alignment?: { offset_seconds?: number | null };
  [key: string]: unknown;
}

export function timestamp(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) throw new Error("timestamp must be finite and non-negative");
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

export function label(segment: TimelineSegment): string {
  return [segment.song ?? "Unknown song", segment.chart].filter(Boolean).join(" ");
}

export function parseTimeline(value: unknown): TimelineDocument {
  if (typeof value !== "object" || value === null || !Array.isArray((value as TimelineDocument).segments)) {
    throw new Error("input JSON must contain a segments array");
  }
  const document = value as TimelineDocument;
  for (const [index, segment] of document.segments.entries()) {
    if (typeof segment !== "object" || segment === null ||
        !Number.isFinite(segment.start_seconds) || !Number.isFinite(segment.end_seconds) ||
        segment.end_seconds <= segment.start_seconds) {
      throw new Error(`invalid segment ${index + 1}`);
    }
  }
  return document;
}
