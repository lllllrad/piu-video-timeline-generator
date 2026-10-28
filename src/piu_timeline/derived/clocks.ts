/** Subframe clocks from retained displacement. Source frames are never resampled. */
import {contracts} from './contracts.ts';
import {frameBounds} from './frame_bounds.ts';
import {compare, linear, lowerBound, median, rms} from './math.ts';
import type {RecordData} from './types.ts';
const F = contracts.local_clock;
const cadenceOf = samples => median(samples.slice(1).map((s, i) => s.time - samples[i].time));

export function* crossingWindows(samples: RecordData[], before: RecordData, after: RecordData): Generator<RecordData[]> {
  const a = samples.findIndex(s => s.time === before.time), b = samples.findIndex(s => s.time === after.time);
  if (a < 0 || b < 0) return;
  const breaks = [0];
  samples.slice(1).forEach((s, i) => { const dt = s.time - samples[i].time; breaks.push(breaks.at(-1) + Number(!(0 < dt && dt <= .05 + 1e-6))); });
  for (let count = samples.length; count >= 16; count--) for (let start = Math.max(0, b - count + 1); start <= Math.min(a, samples.length - count); start++) {
    const end = start + count - 1;
    if (samples[end].time - samples[start].time < .3 || breaks[end] !== breaks[start]) continue;
    yield samples.slice(start, end + 1);
  }
}
export const windows = (samples, before, after) => [...crossingWindows(samples, before, after)];

export function clock(samples: RecordData[], spacing: number): RecordData | null {
  if (samples.length < 16 || samples.at(-1).time - samples[0].time < .3) return null;
  const t = samples.map(s => s.time - samples[0].time), phase = samples.map(s => s.phase);
  const [velocity, intercept] = linear(t, phase), residual = rms(phase.map((v, i) => v - velocity * t[i] - intercept)), cadence = cadenceOf(samples);
  if (velocity <= spacing || residual > Math.max(.75, .5 * cadence * velocity + .75)) return null;
  const half = Math.floor(t.length / 2), first = linear(t.slice(0, half), phase.slice(0, half))[0], last = linear(t.slice(half), phase.slice(half))[0];
  const uncertainty = 6 * residual / Math.max(velocity * (t.at(-1) - t[0]), 1);
  if (Math.abs(first - last) / velocity > .08 + uncertainty) return null;
  return {origin: samples[0].time, velocity, intercept, residual, window: [samples[0].time, samples.at(-1).time]};
}

export class MotionClock {
  state: RecordData;
  chunks: Map<number, RecordData[]>;
  at: Map<number, RecordData>;
  clocks = new Map<number, RecordData | null>();
  constructor(state: RecordData) {
    this.state = state; this.chunks = new Map(); this.at = new Map();
    for (const s of state.samples) { this.at.set(s.time, s); if (!this.chunks.has(s.chunk)) this.chunks.set(s.chunk, []); this.chunks.get(s.chunk).push(s); }
  }
  local(chunk, crossing, phase, phaseError, before, after, cadence): [RecordData | null, number | null] {
    const local = chunk.filter(s => Math.abs(s.time - crossing) <= F.maximum_radius_seconds);
    let best = null;
    for (const window of crossingWindows(local, before, after)) {
      if (best && best.score[0] <= F.position_floor_pixels && window.length < -best.score[1]) break;
      const c = clock(window, this.state.spacing);
      if (!c) continue;
      const proposed = c.origin + (phase - c.intercept) / c.velocity, capture = cadence / 2 + phaseError / c.velocity;
      const errors = [before, after].map(s => Math.abs(s.phase - (c.intercept + c.velocity * (s.time - c.origin)))), limit = capture * c.velocity;
      if (Math.max(...errors) <= limit + 1e-6 && before.time - capture <= proposed && proposed <= after.time + capture) {
        const score = [Math.max(F.position_floor_pixels, c.residual), -window.length, Math.abs((window[0].time + window.at(-1).time) / 2 - crossing), window[0].time];
        if (!best || compare(score, best.score) < 0) best = {score, clock: {...c, selection: F.selection, trimmed_outer_frames: local.length - window.length,
          bracket_phase_errors_pixels: errors, bracket_tolerance_pixels: limit}, capture};
      }
    }
    return best ? [best.clock, best.capture] : [null, null];
  }
  extrapolated(sample, phase, phaseError): RecordData | null {
    const chunk = this.chunks.get(sample.chunk), last = chunk.at(-1), spacing = this.state.spacing;
    if (!(0 < phase - last.phase && phase - last.phase <= 1.1 * spacing)) return null;
    const c = clock(chunk, spacing);
    if (!c) return null;
    const time = c.origin + (phase - c.intercept) / c.velocity;
    if (!(0 < time - last.time && time - last.time <= .25)) return null;
    const samples = this.state.samples, times = samples.map(s => s.time), index = lowerBound(times, time);
    if (!(0 < index && index < times.length)) return null;
    const tail = samples.slice(lowerBound(times, last.time), index + 1);
    if (tail.slice(1).some((s, i) => s.time - tail[i].time > .05 + 1e-6) || tail.slice(1).some(s => s.support >= 2 && s.time <= time)) return null;
    const before = samples[index - 1], after = samples[index], cadence = cadenceOf(chunk), span = c.window[1] - c.window[0];
    const speedError = Math.max(1.5, 3 * c.residual) / span;
    const uncertainty = Math.max(cadence / 2, (phaseError + c.residual + speedError * (time - last.time)) / c.velocity);
    return {target_seconds: time, prediction_uncertainty_seconds: uncertainty, fit_method: 'shared_scroll_clock_extrapolation', motion_clock: c,
      motion_support_end_seconds: last.time, extrapolation_seconds: time - last.time, crossing_source_pts_seconds: [before.source_pts, after.source_pts],
      crossing_frame_seconds: [before.time, after.time], crossing_capture_range: [before.time - uncertainty, after.time + uncertainty]};
  }
  crossing(sample, phase, phaseError): RecordData | null {
    const chunk = this.chunks.get(sample.chunk), index = lowerBound(chunk.map(s => s.phase), phase);
    if (index >= chunk.length) return this.bridge(sample, phase, phaseError) ?? this.extrapolated(sample, phase, phaseError);
    if (index <= 0) return null;
    const lastBefore = chunk[index - 1], after = chunk[index];
    let lower = index - 1;
    while (lower > 0 && Math.abs(chunk[lower - 1].phase - lastBefore.phase) <= F.stationary_phase_epsilon_pixels &&
      0 < chunk[lower].time - chunk[lower - 1].time && chunk[lower].time - chunk[lower - 1].time <= .05 + 1e-6) lower--;
    const before = chunk[lower], stationary = lower < index - 1;
    if (after.phase <= before.phase) return null;
    const fraction = (phase - before.phase) / (after.phase - before.phase), interpolated = before.time + fraction * (after.time - before.time);
    const sourcePhaseError = phaseError;
    phaseError += Math.sqrt(Math.max(0, after.variance - sample.variance));
    if (!this.clocks.has(sample.chunk)) this.clocks.set(sample.chunk, clock(chunk, this.state.spacing));
    let c = this.clocks.get(sample.chunk), capture = 0, rejected = null;
    const cadence = cadenceOf(chunk.slice(Math.max(0, index - 8), index + 8));
    capture = cadence / 2;
    if (c) {
      const proposed = c.origin + (phase - c.intercept) / c.velocity;
      capture = cadence / 2 + phaseError / c.velocity;
      if (!(before.time - capture <= proposed && proposed <= after.time + capture)) { rejected = {clock: c, target_seconds: proposed}; c = null; }
    }
    if (!c) { const [local, error] = this.local(chunk, interpolated, phase, phaseError, before, after, cadence); if (local) { c = local; capture = error; } }
    if (!c) {
      const bounded = frameBounds(chunk, sample, phase, sourcePhaseError, cadence);
      return bounded ? {...bounded, ...(rejected ? {rejected_chunk_clock: rejected} : {})} : null;
    }
    const time = c.origin + (phase - c.intercept) / c.velocity;
    let uncertainty = Math.max(cadence / 2, (phaseError + c.residual) / c.velocity);
    // Repeated positions cannot identify when motion resumed within the capture interval.
    // Keep the original frames: a pause and a stale captured image remain alternatives.
    if (stationary) uncertainty = Math.max(uncertainty, Math.max(time - before.time, after.time - time) + capture);
    return {target_seconds: time, prediction_uncertainty_seconds: uncertainty, fit_method: 'shared_scroll_clock', motion_clock: c,
      ...(rejected ? {rejected_chunk_clock: rejected} : {}),
      ...(stationary ? {stationary_phase_interval: {recording_seconds: [before.time, lastBefore.time],
        source_pts_seconds: [before.source_pts, lastBefore.source_pts], phase: lastBefore.phase,
        frames: index - lower, interpretation: 'scroll_pause_or_repeated_capture'}} : {}), crossing_source_pts_seconds: [before.source_pts, after.source_pts],
      crossing_frame_seconds: [before.time, after.time], crossing_capture_range: [before.time - capture, after.time + capture]};
  }
  fit(track, receptor, layout = null): RecordData | null {
    const {spacing, height} = this.state, bottom = (layout?.note_y_max ?? .95) * height - .55 * spacing;
    const visible = track.points.filter(([t, y]) => receptor + .85 * spacing < y && y < bottom).map(([t, y]) => [t, y, this.at.get(t)]);
    if (!visible.length || !visible.at(-1)[2]) return null;
    const chunk = visible.at(-1)[2].chunk, latest = visible.filter(p => p[2]?.chunk === chunk);
    if (latest.length >= 4 && latest.at(-1)[0] - latest[0][0] >= .065) return this.fitVisible(track, latest, receptor, layout);
    const groups = new Map<number, any[]>();
    for (const p of visible) if (p[2]) { if (!groups.has(p[2].chunk)) groups.set(p[2].chunk, []); groups.get(p[2].chunk).push(p); }
    for (const [key, points] of [...groups].reverse()) {
      if (key === chunk) continue;
      const later = visible.filter(p => p[0] > points.at(-1)[0]);
      if (later.some(p => !p[2] || p[2].support >= 2 || Object.hasOwn(this.state.coordinate_failures ?? {}, p[2].chunk))) return null;
      const r = this.fitVisible(track, points, receptor, layout);
      if (!r) continue;
      const c = r.motion_clock;
      if (!c) return null;
      const native = track.points.filter(([t]) => t > points.at(-1)[0]), limit = .75 + c.velocity * r.prediction_uncertainty_seconds;
      const errors = native.map(([t, y]) => Math.abs(y - (receptor + c.velocity * (r.target_seconds - t))));
      if (!errors.length || Math.max(...errors) > limit || native.some(([t]) => t > r.target_seconds)) return null;
      return {...r, validated_later_observations: native.length, later_observation_maximum_error_pixels: Math.max(...errors), later_observation_tolerance_pixels: limit};
    }
    return null;
  }
  fitVisible(track, visible, receptor, layout): RecordData | null {
    const chunk = visible.at(-1)[2].chunk, spacing = this.state.spacing;
    if (Object.hasOwn(this.state.coordinate_failures ?? {}, chunk) || visible.length < 4 || visible.at(-1)[0] - visible[0][0] < .065) return null;
    const phase = visible.map(p => p[2].phase), y = visible.map(p => p[1]);
    if (phase.at(-1) - phase[0] < .8 * spacing) return null;
    const slope = linear(phase.map(p => p - phase.at(-1)), y)[0];
    if (slope < -1.12 || slope > -.88) return null;
    const offset = track.registration_offsets?.[chunk], intercept = offset != null ? offset - phase.at(-1) : median(y.map((v, i) => v + phase[i] - phase.at(-1)));
    const errors = y.map((v, i) => v + phase[i] - phase.at(-1) - intercept), inliers = errors.filter(v => Math.abs(v) <= .15 * spacing);
    if (inliers.length < Math.max(4, Math.ceil(.85 * visible.length))) return null;
    const residual = rms(inliers);
    let hud = false;
    if (layout?.combo_roi?.length) {
      const [x, top, width, height] = layout.combo_roi, laneX = layout.lanes[track.lane].x, lastY = visible.at(-1)[1] / this.state.height;
      hud = x - .12 <= laneX && laneX <= x + width + .12 && top - .18 <= lastY && lastY <= top + height + .1;
    }
    if (intercept - receptor > (hud ? 6 : 2.5) * spacing) return null;
    const target = phase.at(-1) + intercept - receptor, error = Math.max(.75, 2 * residual, track.registration_uncertainty_pixels ?? 0);
    const r = this.crossing(visible.at(-1)[2], target, error);
    if (!r || !(0 <= r.target_seconds - visible.at(-1)[0] && r.target_seconds - visible.at(-1)[0] <= (hud ? .65 : .25))) return null;
    return {...r, status: 'estimated', reason: null, velocity_pixels_per_second: -(phase.at(-1) - phase[0]) / (visible.at(-1)[0] - visible[0][0]), residual_pixels: residual,
      motion_support_points: visible.length, motion_target_phase: target, motion_chunk: chunk, observed_phase_slope: slope};
  }
  bridge(sample, phase, error): RecordData | null {
    const positions = this.state.registered_positions, records = this.state.coordinate_registration?.chunks ?? [];
    if (!positions) return null;
    const fitted = records.filter(r => r.status === 'fitted'), first = fitted.find(r => r.chunk === sample.chunk);
    if (!first) return null;
    const before = this.chunks.get(sample.chunk), end = before.at(-1), old = Object.fromEntries(first.head_offsets.map(h => [h.note, h.offset_pixels])), choices = [];
    for (const record of fitted) {
      const after = this.chunks.get(record.chunk), dt = after[0].time - end.time;
      if (!(0 < dt && dt <= .1 + 1e-6) || after[0].time - sample.time > .25) continue;
      const newer = Object.fromEntries(record.head_offsets.map(h => [h.note, h.offset_pixels]));
      const anchors = Object.keys(old).filter(id => Object.hasOwn(newer, id) && [[before, old[id]], [after, newer[id]]].every(([block, offset]) => {
        const observed = block.filter(s => Object.hasOwn(positions[s.time] ?? {}, id)).map(s => [s.time, positions[s.time][id][1] + s.phase - offset]);
        return observed.length >= 4 && observed.at(-1)[0] - observed[0][0] >= .065 && Math.max(...observed.map(p => Math.abs(p[1]))) <= 1.5;
      }));
      if (anchors.length < 2) continue;
      const shifts = anchors.map(i => old[i] - newer[i]), shift = median(shifts), disagreement = Math.max(...shifts.map(s => Math.abs(s - shift)));
      if (disagreement > 1) continue;
      const lanes = new Set(before.flatMap(s => anchors.filter(i => positions[s.time]?.[i]).map(i => positions[s.time][i][0])));
      if (lanes.size < 2 && Math.max(...anchors.map(i => old[i])) - Math.min(...anchors.map(i => old[i])) <= .65 * this.state.spacing) continue;
      const middle = this.state.samples.filter(s => end.time <= s.time && s.time <= after[0].time), proof = [];
      let previous = end.phase, valid = true;
      for (let j = 1; j < middle.length; j++) {
        const a = middle[j - 1], b = middle[j], values = anchors.filter(i => positions[b.time]?.[i]).map(i => old[i] - positions[b.time][i][1]), dt = b.time - a.time;
        if (!(0 < dt && dt <= .05 + 1e-6) || !values.length || Math.max(...values) - Math.min(...values) > 1.5 || Object.hasOwn(this.state.coordinate_failures ?? {}, b.chunk)) { valid = false; break; }
        const value = median(values);
        if (!(-.75 <= value - previous && value - previous <= 30 * this.state.spacing * dt)) { valid = false; break; }
        previous = value; proof.push(b.source_pts);
      }
      if (!valid || Math.abs(previous - (after[0].phase + shift)) > 1.5) continue;
      const translated = phase - shift;
      if (!(after[0].phase < translated && translated <= after.at(-1).phase)) continue;
      const r = this.crossing(after[0], translated, error + Math.max(.75, disagreement));
      if (!r || !(0 <= r.target_seconds - sample.time && r.target_seconds - sample.time <= .25)) continue;
      choices.push({...r, crossing_method: r.fit_method, fit_method: 'shared_scroll_registered_block_transfer', coordinate_bridge: {from_chunk: sample.chunk, to_chunk: record.chunk,
        anchor_notes: anchors.map(Number).sort((a, b) => a - b), phase_offset_pixels: shift, maximum_anchor_disagreement_pixels: disagreement, intermediate_source_pts_seconds: proof}, clock_target_phase: translated});
    }
    return choices.length === 1 ? choices[0] : null;
  }
}

export function crossing(state, sample, phase, error) { return new MotionClock(state).crossing(sample, phase, error); }
export function fit(state, track, receptor, layout) { return new MotionClock(state).fit(track, receptor, layout); }
export function fitMany(state, tracks, receptor, layout) { const c = new MotionClock(state); return tracks.map(t => c.fit(t, receptor, layout)); }
export function bridge(state, sample, phase, error) { return new MotionClock(state).bridge(sample, phase, error); }
