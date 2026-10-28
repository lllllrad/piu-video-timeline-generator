/** Evaluate concrete pause and relative-speed models against saved native tracks. */
import {linear, rms} from './math.ts';
import {fitTrack} from './tracks.ts';
import type {RecordData} from './types.ts';

export function models(data: RecordData, kind: 'pause' | 'speed'): RecordData[] {
  return (data.chart_policy?.gimmick_candidates ?? []).filter(e => e.kind === (kind === 'pause' ? 'scroll_pause' : 'scroll_speed_change') && e.review_status !== 'rejected').map(e => {
    if (kind === 'pause') return {id: e.id, start: e.playback_start_seconds, end: e.playback_end_seconds, speed_multiplier: 0, boundary_uncertainty_seconds: e.boundary_uncertainty_seconds};
    const origin = e.playback_start_seconds - e.start_seconds;
    return {id: e.id, start: e.playback_start_seconds, end: e.playback_end_seconds, transition_range: e.transition_range_seconds.map(t => origin + t), ratio: e.speed_multiplier, ratio_range: e.speed_ratio_range};
  });
}
export const movingTime = (times: number[], pauses: RecordData[]): number[] => times.map(t => pauses.reduce((v, p) => v - Math.min(Math.max(t - p.start, 0), p.end - p.start), t));

export function pausePath(note: RecordData, data: RecordData, receptor: number, spacing: number, scale: number): RecordData | null {
  let points = note.points ?? [], pauses = data.scroll_pause_model ?? [];
  if (points.length < 4 || !pauses.length) return null;
  pauses = pauses.filter(p => points[0][0] <= p.end && points.at(-1)[0] >= p.start).sort((a, b) => a.start - b.start);
  if (!pauses.length) return null;
  const failed = {supported: false, basis: 'configured_pause_native_trajectory', velocity: 0, target: null};
  const bottom = (data.layout?.note_y_max ?? .95) * data.analysis_height * scale - .55 * spacing;
  points = points.filter(([, y]) => y * scale > receptor + .85 * spacing && y * scale < bottom);
  if (points.length < 8 || points.filter(([t]) => t < pauses[0].start).length < 4 || points.filter(([t]) => t > pauses.at(-1).end).length < 4) return failed;
  for (const p of pauses) {
    const interior = points.filter(([t]) => p.start <= t && t <= p.end).map(([, y]) => y * scale);
    if (interior.length < 4 || Math.max(...interior) - Math.min(...interior) > Math.max(.75, .04 * spacing)) return failed;
  }
  const times = movingTime(points.map(([t]) => t), pauses), origin = times.at(-1), y = points.map(([, y]) => y * scale);
  const [speed, intercept] = linear(times.map(t => t - origin), y), residual = rms(y.map((v, i) => v - (speed * (times[i] - origin) + intercept)));
  if (speed >= -spacing || residual > Math.max(.75, .04 * spacing)) return failed;
  let target = origin + (receptor - intercept) / speed;
  for (const p of pauses) if (target >= p.start - Math.max(.75, residual) / Math.abs(speed)) {
    if (Math.abs(target - p.start) <= Math.max(.75, residual) / Math.abs(speed)) return failed;
    target += p.end - p.start;
  }
  if (!(0 <= target - points.at(-1)[0] && target - points.at(-1)[0] <= .25)) return failed;
  return {supported: true, basis: 'configured_pause_native_trajectory', velocity: speed, target, residual_pixels: residual,
    position_model: {kind: 'pause', pauses, speed, origin, intercept}};
}

export function speedPath(note: RecordData, data: RecordData, receptor: number, spacing: number, scale: number): RecordData | null {
  const points = note.points ?? [];
  if (points.length < 8) return null;
  const owners = (data.scroll_speed_model ?? []).filter(m => points[0][0] < m.transition_range[0] && points.at(-1)[0] > m.transition_range[1]);
  if (!owners.length) return null;
  const failed = {supported: false, basis: 'configured_speed_native_trajectory', velocity: 0, target: null};
  if (owners.length !== 1) return failed;
  const model = owners[0], [lo, hi] = model.transition_range, center = (lo + hi) / 2, ratio = model.ratio;
  const bottom = (data.layout?.note_y_max ?? .95) * data.analysis_height * scale - .55 * spacing;
  const kept = points.filter(([t, y]) => model.start <= t && t <= model.end && y * scale > receptor + .85 * spacing && y * scale < bottom);
  if (kept.filter(([t]) => t < lo).length < 4 || kept.filter(([t]) => t > hi).length < 4) return failed;
  const times = kept.map(([t]) => t - center), clock = times.map(t => t < 0 ? t : ratio * t), y = kept.map(([, y]) => y * scale);
  const [speed, intercept] = linear(clock, y), residual = rms(y.map((v, i) => v - (speed * clock[i] + intercept)));
  if (speed >= -spacing || residual > Math.max(.75, .04 * spacing)) return failed;
  const phase = (receptor - intercept) / speed, target = center + (phase < 0 ? phase : phase / ratio);
  if (!(kept.at(-1)[0] <= target && target <= Math.min(model.end, kept.at(-1)[0] + .25))) return failed;
  return {supported: true, basis: 'configured_speed_native_trajectory', velocity: speed * (target >= center ? ratio : 1), target,
    position_model: {kind: 'speed', model, center, speed, intercept}};
}

export function classify(data: RecordData, records: RecordData[], kind: 'pause' | 'speed'): RecordData[][] {
  const remaining = [], expected = [];
  for (const r of records) {
    const owners = [], lo = r.visible_start_seconds, hi = r.visible_end_seconds;
    if (kind === 'pause') for (const p of data.scroll_pause_model ?? []) {
      const e = p.boundary_uncertainty_seconds;
      if (r.reason === 'possible_scroll_stop_or_capture_freeze' && p.start - e <= lo && hi <= p.end + e) owners.push(p.id);
      else if (r.reason === 'scroll_speed_change') {
        const stoppedAfter = Math.abs(r.velocity_after_pixels_per_second) <= r.velocity_error_after, stoppedBefore = Math.abs(r.velocity_before_pixels_per_second) <= r.velocity_error_before;
        if (stoppedAfter && lo - e <= p.start && p.start <= hi + e || stoppedBefore && lo - e <= p.end && p.end <= hi + e) owners.push(p.id);
      }
    } else if (r.reason === 'scroll_speed_change') {
      const a = -r.velocity_before_pixels_per_second, b = -r.velocity_after_pixels_per_second, ea = r.velocity_error_before, eb = r.velocity_error_after;
      if (a > ea && b > eb) {
        const bounds = [(b - eb) / (a + ea), (b + eb) / (a - ea)];
        for (const m of data.scroll_speed_model ?? []) if (lo <= m.transition_range[1] && hi >= m.transition_range[0] && Math.max(bounds[0], m.ratio_range[0]) <= Math.min(bounds[1], m.ratio_range[1])) owners.push(m.id);
      }
    }
    if (owners.length) expected.push({...r, native_reason: r.reason, reason: kind === 'pause' ? 'configured_scroll_pause' : 'configured_scroll_speed_change', gimmick_candidates: owners, ...(kind === 'pause' ? {speed_multiplier: 0} : {})});
    else remaining.push(r);
  }
  return [remaining, expected];
}

export function processingPaths(notes: RecordData[], data: RecordData, receptor: number, spacing: number, scale: number): RecordData[] {
  const chunks = new Map<number, RecordData[]>();
  for (const s of data.scroll_motion?.samples ?? []) { if (!chunks.has(s.chunk)) chunks.set(s.chunk, []); chunks.get(s.chunk).push(s); }
  return notes.map(note => {
    const configured = pausePath(note, data, receptor, spacing, scale) ?? speedPath(note, data, receptor, spacing, scale);
    if (configured) return configured;
    const points = note.points ?? [], failed = {supported: false, basis: 'unsupported_native_trajectory', velocity: 0, target: null};
    if (points.length < 4) return failed;
    const bridge = note.coordinate_bridge ?? {}, phase = Object.hasOwn(note, 'clock_target_phase') ? note.clock_target_phase : note.motion_target_phase;
    const chunk = bridge.to_chunk ?? note.motion_chunk, samples = chunks.get(chunk) ?? [];
    if (phase != null && samples.length && note.timing_reconstruction?.status !== 'failed') {
      const i = samples.findIndex((a, j) => j < samples.length - 1 && a.phase <= phase && phase < samples[j + 1].phase && 0 < samples[j + 1].time - a.time && samples[j + 1].time - a.time <= .05);
      // A transferred coordinate block can bound a crossing without any affine
      // clock. Its own measured phase step still supplies a display-path slope.
      const transferred = i >= 0 ? -(samples[i + 1].phase - samples[i].phase) / (samples[i + 1].time - samples[i].time) : 0;
      const transferVelocity = note.motion_clock ? -note.motion_clock.velocity : transferred;
      const velocity = (Object.keys(bridge).length ? transferVelocity : (note.velocity_pixels_per_second ?? 0)) * scale;
      if (i >= 0 && velocity < -spacing) {
        const a = samples[i], b = samples[i + 1], target = a.time + (phase - a.phase) / (b.phase - a.phase) * (b.time - a.time);
        return {supported: true, basis: 'registered_native_displacement', velocity, target,
          position_model: {kind: 'registered', chunk, phase, from_chunk: bridge.from_chunk ?? null, motion_target_phase: note.motion_target_phase, receptor, scale}};
      }
    }
    const fitted = fitTrack({lane: note.lane, points: points.map(([t, y]) => [t, y * scale])}, receptor, spacing);
    if (fitted.status !== 'estimated' || fitted.prediction_uncertainty_seconds > .05 || fitted.velocity_pixels_per_second >= -spacing) return failed;
    return {supported: true, basis: 'bounded_native_trajectory', velocity: fitted.velocity_pixels_per_second, target: fitted.target_seconds,
      position_model: {kind: 'linear', receptor, velocity: fitted.velocity_pixels_per_second, target: fitted.target_seconds}};
  });
}
