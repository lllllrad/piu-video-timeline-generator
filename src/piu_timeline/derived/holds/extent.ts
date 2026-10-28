/** A rigid body's length must satisfy every independently bounded endpoint pair. */
export const format = {schema: 1, minimum_frames: 4, minimum_span_seconds: .065, method: 'registered_endpoint_interval_intersection'};
export interface Measurement {
  time: number; source_pts_seconds: number; head_y: number; tail_y: number;
  head_uncertainty?: number; tail_uncertainty?: number;
}
export function intersect(samples: Measurement[]) {
  let lower = 0, upper = Infinity, last = -Infinity, lastPTS = -Infinity;
  const qualified: Measurement[] = [], unverified: number[] = [];
  for (const s of samples) {
    if (![s.time, s.source_pts_seconds, s.head_y, s.tail_y].every(Number.isFinite) || s.time <= last || s.source_pts_seconds <= lastPTS) throw Error('Invalid endpoint observation timeline');
    last = s.time; lastPTS = s.source_pts_seconds;
    if (s.tail_y <= s.head_y) return {status: 'conflict', reason: 'reversed_endpoint_positions'};
    if (![s.head_uncertainty, s.tail_uncertainty].every(v => Number.isFinite(v) && v > 0)) { unverified.push(s.source_pts_seconds); continue; }
    const length = s.tail_y - s.head_y, uncertainty = s.head_uncertainty + s.tail_uncertainty;
    lower = Math.max(lower, length - uncertainty); upper = Math.min(upper, length + uncertainty);
    qualified.push(s);
  }
  if (lower > upper + 1e-9) return {status: 'conflict', reason: 'incompatible_endpoint_length_intervals'};
  if (qualified.length < format.minimum_frames || qualified.at(-1).time - qualified[0].time < format.minimum_span_seconds - 1e-9) {
    return {status: 'unverified', reason: 'insufficient_registered_endpoint_pairs'};
  }
  return {status: 'consistent', format, length_range_pixels: [lower, Math.max(lower, upper)],
    source_pts_seconds: qualified.map(s => s.source_pts_seconds), unverified_source_pts_seconds: unverified};
}
