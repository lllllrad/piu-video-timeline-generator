/** Concrete scroll-speed proposals from registered native displacement. */
import {contracts} from './contracts.ts';
import {equal, linear, lowerBound, mean, median, rms, sum, upperBound} from './math.ts';
import type {RecordData} from './types.ts';
const F = contracts.speed;

export function window(samples: RecordData[], spacing: number): [RecordData | null, string | null] {
  if (samples.some(s => s.coordinate_status === 'failed')) return [null, 'registered_coordinate_failure'];
  if (samples.length < 12 || samples.at(-1).time - samples[0].time < .24) return [null, 'insufficient_native_span'];
  const independent = samples.filter(s => s.support >= 2 && s.lanes >= 2).length;
  if (independent / samples.length < F.minimum_independent_fraction) return [null, 'insufficient_independent_peers'];
  const times = samples.map(s => s.time - samples[0].time), phase = samples.map(s => s.phase), [speed, intercept] = linear(times, phase);
  if (speed <= spacing || phase.at(-1) - phase[0] < .5 * spacing) return [null, 'stationary_or_small_displacement'];
  const errors = phase.map((v, i) => v - speed * times[i] - intercept), residual = rms(errors);
  const cadence = median(times.slice(1).map((t, i) => t - times[i])), limit = Math.max(.75, .55 * cadence * speed + .5);
  if (residual > limit) return [null, 'nonlinear_or_inconsistent_displacement'];
  const center = mean(times), spread = sum(times.map(t => (t - center) ** 2));
  const error = Math.max(3 * Math.sqrt(sum(errors.map(e => e * e)) / Math.max(1, times.length - 2) / spread), 1.5 / times.at(-1));
  if (error > .15 * speed) return [null, 'speed_uncertainty_too_wide'];
  return [{start: samples[0].time, end: samples.at(-1).time, speed, error, intercept, residual, position_limit: limit,
    source_pts_seconds: [samples[0].source_pts, samples.at(-1).source_pts], frames: samples.length, independent_frames: independent,
    median_peer_heads: median(samples.map(s => s.support))}, null];
}
const ratioBounds = (before, after) => [(after.speed - after.error) / (before.speed + before.error), (after.speed + after.error) / (before.speed - before.error)];

export function transition(before: RecordData, after: RecordData, samples: RecordData[], spacing: number): RecordData | null {
  const ratio = after.speed / before.speed, bounds = ratioBounds(before, after);
  if (bounds[0] <= 1 && 1 <= bounds[1] || Math.abs(ratio - 1) < .15) return null;
  const gap = after.start - before.end;
  if (!(-1e-6 <= gap && gap <= .3 + 1e-6)) return null;
  const origin = before.start, relative = after.start - origin;
  const crossing = (before.intercept - after.intercept + after.speed * relative) / (after.speed - before.speed), time = origin + crossing;
  const cadence = median(samples.slice(1).map((s, i) => s.time - samples[i].time));
  if (!(before.end - cadence <= time && time <= after.start + cadence)) return null;
  const middle = samples.filter(s => before.end <= s.time && s.time <= after.start), phase = before.intercept + before.speed * crossing;
  const residuals = middle.map(s => Math.abs(s.phase - (phase + (s.time - time) * (s.time < time ? before.speed : after.speed))));
  if (residuals.length && Math.max(...residuals) > Math.max(before.position_limit, after.position_limit) + 1.5) return null;
  return {start_seconds: before.start, end_seconds: after.end, transition_range_seconds: [before.end, after.start], estimated_transition_seconds: time,
    speed_multiplier: ratio, speed_ratio_range: bounds, before, after, lane_spacing_pixels: spacing,
    reference_speed_lane_spacings_per_second: before.speed / spacing, result_speed_lane_spacings_per_second: after.speed / spacing};
}

export function estimate(data: RecordData): RecordData {
  const motion = data.scroll_motion ?? {};
  if (motion.format?.method !== 'registered_peer_displacement') return {format: F, status: 'unavailable', reason: 'registered_native_displacement_required', transitions: []};
  const lanes = data.layout?.lanes ?? [];
  if (lanes.length < 2) return {format: F, status: 'unavailable', reason: 'lane_geometry_required', transitions: []};
  const xs = lanes.map(l => l.x * data.analysis_width), spacing = median(xs.slice(1).map((x, i) => x - xs[i]));
  const chunks = new Map<number, RecordData[]>();
  for (const s of motion.samples) { if (!chunks.has(s.chunk)) chunks.set(s.chunk, []); chunks.get(s.chunk).push(s); }
  const registered = equal(motion.coordinate_registration?.format, contracts.registration), proposals = [], rejected = {};
  let accepted = 0;
  for (const [chunk, samples] of chunks) {
    const times = samples.map(s => s.time), windows = [];
    for (let i = 0; i < samples.length - 11; i += 3) {
      const end = upperBound(times, times[i] + F.window_seconds + 1e-6), [fitted, reason] = window(samples.slice(i, end), spacing);
      if (fitted) { windows.push(fitted); accepted++; } else rejected[reason] = (rejected[reason] ?? 0) + 1;
    }
    const starts = windows.map(w => w.start);
    for (const before of windows) for (const after of windows.slice(lowerBound(starts, before.end - 1e-6))) {
      if (after.start - before.end > .3 + 1e-6) break;
      const p = transition(before, after, samples, spacing);
      if (p) proposals.push({...p, motion_chunk: chunk});
    }
  }
  proposals.sort((a, b) => (a.transition_range_seconds[1] - a.transition_range_seconds[0]) - (b.transition_range_seconds[1] - b.transition_range_seconds[0]) ||
    (a.speed_ratio_range[1] - a.speed_ratio_range[0]) - (b.speed_ratio_range[1] - b.speed_ratio_range[0]));
  const kept = [];
  for (const p of proposals) {
    const [lo, hi] = p.transition_range_seconds;
    if (kept.some(q => p.motion_chunk === q.motion_chunk && lo <= q.transition_range_seconds[1] + .05 && hi >= q.transition_range_seconds[0] - .05 &&
      p.speed_ratio_range[0] <= q.speed_ratio_range[1] && p.speed_ratio_range[1] >= q.speed_ratio_range[0])) continue;
    kept.push(p);
  }
  kept.sort((a, b) => a.estimated_transition_seconds - b.estimated_transition_seconds);
  kept.forEach((p, i) => {
    const reasons = [];
    if (!registered) reasons.push('joint_native_coordinate_registration_required');
    const samples = chunks.get(p.motion_chunk), t = p.before.end, u = p.after.start;
    const [before] = window(samples.filter(s => t - F.confirmation_seconds - 1e-6 <= s.time && s.time <= t + 1e-6), spacing);
    const [after] = window(samples.filter(s => u - 1e-6 <= s.time && s.time <= u + F.confirmation_seconds + 1e-6), spacing);
    let confirmed = false;
    if (before && after && Math.min(before.end - before.start, after.end - after.start) >= .4 - 1e-6) {
      const ratio = after.speed / before.speed, bounds = ratioBounds(before, after);
      confirmed = !(bounds[0] <= 1 && 1 <= bounds[1]) && Math.abs(ratio - 1) >= .15 && p.speed_ratio_range[0] <= ratio && ratio <= p.speed_ratio_range[1];
      p.long_flank_confirmation = {before, after, speed_multiplier: ratio, speed_ratio_range: bounds, consistent: confirmed};
    }
    if (!confirmed) reasons.push('longer_native_flanks_do_not_confirm_change');
    if ((p.speed_ratio_range[1] - p.speed_ratio_range[0]) / p.speed_multiplier > .15) reasons.push('ratio_uncertainty_too_wide');
    if (p.transition_range_seconds[1] - p.transition_range_seconds[0] > .1 + 1e-6) reasons.push('transition_bracket_too_wide');
    if (Math.min(p.before.median_peer_heads, p.after.median_peer_heads) < 3) reasons.push('fewer_than_three_peer_heads');
    if (kept.some((q, j) => j !== i && Math.abs(q.estimated_transition_seconds - p.estimated_transition_seconds) < .6)) reasons.push('nearby_changes_need_complex_motion_review');
    Object.assign(p, {auto_recordable: !reasons.length, review_reasons: reasons});
  });
  return {format: F, status: kept.length ? 'measured' : 'no_verified_speed_transition', coordinate_registration: motion.coordinate_registration?.format ?? null,
    transitions: kept, stable_windows: accepted, rejected_windows: rejected,
    semantics: 'Upward-positive screen velocity. Ratios are measured, not forced to simple subdivisions; absence of a proposal does not clear warnings.'};
}
