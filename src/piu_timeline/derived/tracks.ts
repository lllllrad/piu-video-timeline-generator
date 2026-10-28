import {linear, mean, median, rms, std, sum} from './math.ts';
import {refine} from './registration.ts';
import type {RecordData} from './types.ts';

export function registered(tracks: RecordData[], timeline: RecordData[], height: number, spacing: number, receptor: number, bottom: number): RecordData {
  const at = new Map<number, RecordData>();
  tracks.forEach((track, i) => { for (const [t, y] of track.points) if (receptor + .85 * spacing < y && y < bottom - .55 * spacing) {
    if (!at.has(t)) at.set(t, {}); at.get(t)[i] = [track.lane, y];
  } });
  const samples = [];
  let previous = null, anchor = null, chunk = -1;
  for (const native of timeline) {
    const time = native.time, current = at.get(time) ?? {};
    let displacement = null, observed = null, support = 0, lanes = 0, scatter = 0, basis = 'unsupported';
    if (previous && 0 < time - previous.time && time - previous.time <= .05 + 1e-6) {
      const before = at.get(previous.time) ?? {};
      const pairs = Object.keys(before).filter(i => Object.hasOwn(current, i)).map(i => [before[i][1] - current[i][1], current[i][0], Number(i)]);
      if (pairs.length) {
        const center = median(pairs.map(p => p[0])); observed = center;
        const kept = pairs.filter(p => Math.abs(p[0] - center) <= 1.5);
        support = kept.length; lanes = new Set(kept.map(p => p[1])).size;
        if (support >= 2 && (lanes >= 2 || Math.max(...kept.map(p => current[p[2]][1])) - Math.min(...kept.map(p => current[p[2]][1])) > .65 * spacing) && -.75 <= center && center <= spacing * 30 * (time - previous.time)) {
          displacement = Math.max(0, median(kept.map(p => p[0]))); scatter = Math.max(.35, std(kept.map(p => p[0])));
          basis = 'independent_registered_peers'; anchor = [time, new Set(kept.map(p => p[2]))];
        } else if (pairs.length === 1 && anchor && time - anchor[0] <= .25 + 1e-6 && anchor[1].has(pairs[0][2]) && -.75 <= pairs[0][0] && pairs[0][0] <= spacing * 30 * (time - previous.time)) {
          displacement = Math.max(0, pairs[0][0]); support = lanes = 1; scatter = .75; basis = 'registered_identity_continuation';
        }
      }
    }
    let phase = 0, variance = 0;
    if (displacement === null) { chunk++; anchor = null; }
    else { phase = samples.at(-1).phase + displacement; variance = samples.at(-1).variance + scatter ** 2; }
    samples.push({...native, phase, pairwise_phase_pixels: phase, observed_peer_displacement_pixels: observed, variance, chunk,
      support: displacement !== null ? support : 0, lanes: displacement !== null ? lanes : 0, displacement_basis: basis});
    previous = native;
  }
  return {...refine(samples, tracks, receptor, spacing, bottom), registered_positions: Object.fromEntries(at)};
}

export function fitTrack(track: RecordData, receptor: number, spacing: number): RecordData {
  const result: RecordData = {lane: track.lane, points: track.points, status: 'excluded', reason: null, target_seconds: null};
  const visible = track.points.filter(p => p[1] > receptor + .85 * spacing);
  if (visible.length < 4 || visible.at(-1)[0] - visible[0][0] < .065) return {...result, reason: 'insufficient_track'};
  const points = visible.slice(-12), t = points.map(p => p[0] - points.at(-1)[0]), y = points.map(p => p[1]);
  const [velocity, intercept] = linear(t, y), residual = rms(y.map((v, i) => v - velocity * t[i] - intercept));
  Object.assign(result, {velocity_pixels_per_second: velocity, residual_pixels: residual});
  if (velocity >= -spacing) return {...result, reason: 'stopped_or_reverse_scroll'};
  const half = Math.floor(points.length / 2), first = linear(t.slice(0, half), y.slice(0, half)), last = linear(t.slice(half), y.slice(half));
  const change = Math.abs(first[0] - last[0]) / Math.max(Math.abs(velocity), 1);
  result.speed_change_fraction = change;
  const quantization = 2 / Math.max(Math.abs(velocity) * (t.at(-1) - t[half]), 1);
  const variance = (ts, ys, fit) => {
    const errors = ys.map((v, i) => v - fit[0] * ts[i] - fit[1]);
    return sum(errors.map(v => v * v)) / Math.max(1, ts.length - 2) / Math.max(sum(ts.map(v => (v - mean(ts)) ** 2)), 1e-9);
  };
  const slopeError = 3 * Math.sqrt(variance(t.slice(0, half), y.slice(0, half), first) + variance(t.slice(half), y.slice(half), last)) / Math.abs(velocity);
  if (residual > spacing * .14 || change > .18 + quantization + slopeError) {
    const gaps = points.slice(1).flatMap((p, i) => p[0] - points[i][0] > .06 ? [i] : []);
    if (gaps.length) {
      const latest = points.slice(gaps.at(-1) + 1);
      if (latest.length >= 4 && latest.at(-1)[0] - latest[0][0] >= .065) {
        const recovered = fitTrack({...track, points: latest}, receptor, spacing);
        if (recovered.status === 'estimated') return {...recovered, points: result.points, fit_method: 'linear_after_occlusion'};
      }
    }
    return {...result, reason: 'variable_speed_or_tracking_error'};
  }
  const target = points.at(-1)[0] + (receptor - intercept) / velocity, extrapolation = target - points.at(-1)[0];
  if (!(0 <= extrapolation && extrapolation <= .25) || intercept - receptor > 2.5 * spacing) return {...result, reason: 'receptor_not_observed_closely'};
  const step = median(points.slice(1).map((p, i) => p[0] - points[i][0]));
  let heldSince = points[0][0], holdSpan = 0;
  points.slice(1).forEach((p, i) => { if (Math.abs(p[1] - points[i][1]) > .75) heldSince = p[0]; holdSpan = Math.max(holdSpan, p[0] - heldSince); });
  return {...result, status: 'estimated', target_seconds: target, prediction_uncertainty_seconds: Math.max(residual / Math.abs(velocity), (track.registration_uncertainty_pixels ?? 0) / Math.abs(velocity), (step + holdSpan) / 2)};
}
