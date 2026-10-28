/** Measured phase bounds without assuming motion between captured images. */
import {lowerBound} from './math.ts';
import type {RecordData} from './types.ts';

export function frameBounds(samples: RecordData[], sample: RecordData, phase: number, error: number, cadence: number): RecordData | null {
  if (![phase, error, cadence].every(Number.isFinite) || error < 0 || cadence <= 0) return null;
  // Uncertainty may grow after the last observation of the tested head.
  const uncertainty = s => error + Math.sqrt(Math.max(0, s.variance - sample.variance));
  const lower = samples.map(s => s.phase + uncertainty(s)), upper = samples.map(s => s.phase - uncertainty(s));
  const crossing = lowerBound(samples.map(s => s.phase), phase);
  let a = crossing - 1, b = crossing;
  while (a >= 0 && lower[a] >= phase) a--;
  while (b < samples.length && upper[b] <= phase) b++;
  if (a < 0 || b >= samples.length) return null;
  // Include the entire repeated-image plateau, rather than its final copy.
  while (a > 0 && Math.abs(samples[a - 1].phase - samples[a].phase) <= 1e-6) a--;
  const retained = samples.slice(a, b + 1);
  if (retained.slice(1).some((s, i) => !(0 < s.time - retained[i].time && s.time - retained[i].time <= .05 + 1e-6) || s.phase < retained[i].phase)) return null;
  const before = samples[a], after = samples[b], capture = cadence / 2;
  const range = [before.time - capture, after.time + capture], time = (range[0] + range[1]) / 2;
  return {target_seconds: time, prediction_uncertainty_seconds: (range[1] - range[0]) / 2,
    fit_method: 'shared_scroll_frame_bounds', motion_clock: null,
    crossing_frame_seconds: [before.time, after.time], crossing_source_pts_seconds: [before.source_pts, after.source_pts],
    crossing_capture_range: range, native_clock_warning: {reason: 'shared_subframe_clock_unresolved',
      interpretation: 'observed_crossing_without_subframe_clock', phase_error_pixels: error,
      boundary_phase_ranges: [[before.phase - uncertainty(before), lower[a]], [upper[b], after.phase + uncertainty(after)]]}};
}
