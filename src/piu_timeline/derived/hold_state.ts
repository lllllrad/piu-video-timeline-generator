/** Sustained responses and receptor onsets from saved observations, never switch presses. */
import {lowerBound, upperBound, median, equal} from './math.ts';
import type {RecordData} from './types.ts';
import {Store, implementation, artifactCurrent} from './pipeline/store.ts';
import {readFileSync, existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {parseData} from './json.ts';
import {inputNotes} from './holds/input.ts';
export interface Geometry {receptor: number; spacing: number; note_scale: number; edge_tolerance: number}
type Context = Record<string, RecordData[]>;

export function recognitionWindow(data: RecordData, hold: RecordData, geometry: Geometry): number[] {
  const lower = hold.start_censored ? hold.start_range[1] : hold.start_range[0];
  let upper = hold.end_range ? hold.end_range[1] : hold.last_body_seconds;
  const tail = hold.tail_note;
  if (tail != null) {
    const speed = Math.abs(data.notes[tail].velocity_pixels_per_second ?? 0) * geometry.note_scale;
    if (speed > 0) upper += geometry.edge_tolerance * geometry.spacing / speed;
    const notes = inputNotes(data.notes), end = hold.end_range;
    const tailTarget = end ? (end[0] + end[1]) / 2 : notes[tail].target_seconds;
    const following = Number.isFinite(tailTarget) ? notes.flatMap((n, index) => n.status === 'estimated' && Number.isFinite(n.target_seconds) &&
      n.lane === hold.lane && !hold.covered_notes.includes(index) && n.target_seconds > tailTarget
      ? [n.target_seconds - n.prediction_uncertainty_seconds] : []) : [];
    if (following.length) upper = Math.min(upper, ...following);
  }
  return [lower, Math.max(lower, upper)];
}
export function contextualSupport(data: RecordData, frames: RecordData[], receptor: number, spacing: number, holds: RecordData[] = [], requireGeometry = false): Context {
  const times = frames.map(f => f.playback_seconds), events: [number, RecordData][] = [];
  for (const kind of ['combo_events', 'judgment_events']) (data[kind] ?? []).forEach((event, index) => {
    const lo = event.lower_seconds, hi = event.upper_seconds;
    const positive = kind === 'combo_events' ? (event.delta ?? 0) > 0 : ['PERFECT', 'GREAT', 'GOOD', 'BAD'].includes(event.label);
    if (positive && 0 <= hi - lo && hi - lo <= .12) events.push([hi, {kind, index, range: [lo, hi]}]);
  });
  events.sort((a, b) => a[0] - b[0]);
  const eventTimes = events.map(e => e[0]), result: Context = {};
  frames.forEach((frame, fi) => {
    const values = frame.receptor_white_fraction, time = frame.playback_seconds;
    if (!values || frame.common_receptor_flash) return;
    const nearby = events.slice(lowerBound(eventTimes, time - .04), upperBound(eventTimes, time + .04)).map(e => e[1]);
    if (!nearby.length) return;
    const previous = frames.slice(lowerBound(times, time - .15), upperBound(times, time - .025));
    if (previous.length < 3 || previous.some(p => !p.receptor_white_fraction)) return;
    values.forEach((value, lane) => {
      if (value < .4) return;
      const samples = previous.map(p => p.receptor_white_fraction[lane]).sort((a, b) => a - b), index = (samples.length - 1) * .25;
      const baseline = samples[Math.floor(index)] + (samples[Math.ceil(index)] - samples[Math.floor(index)]) * (index % 1);
      const others = values.filter((_, i) => i !== lane);
      if (value - baseline < .16 || others.length && value - median(others) < .2) return;
      const body = !requireGeometry && frame.bodies.some(b => b.lane === lane && b.top <= receptor + .8 * spacing && b.bottom >= receptor + .6 * spacing);
      const established = holds.some(h => h.lane === lane && h.start_range[1] <= time && time <= (h.end_range ? h.end_range[0] : h.last_body_seconds));
      if (body || established) result[`${fi},${lane}`] = nearby;
    });
  });
  return result;
}
export function recognitionSegments(frames: RecordData[], times: number[], hold: RecordData, contextual: Context, window?: number[] | null): RecordData {
  const start = hold.start_range, lane = hold.lane, segments: RecordData[] = [];
  const supportStart = window ? window[0] : hold.start_censored ? start[1] : start[0];
  const end = window ? window[1] : hold.end_range ? hold.end_range[1] : hold.last_body_seconds;
  for (let fi = lowerBound(times, supportStart); fi < upperBound(times, end); fi++) {
    const frame = frames[fi], corroboration = contextual[`${fi},${lane}`] ?? [];
    if (frame.receptor_lit[lane] !== true && !corroboration.length) continue;
    const time = frame.playback_seconds, pts = frame.source_pts_seconds;
    if (segments.length && time - segments.at(-1).upper_seconds <= .075) Object.assign(segments.at(-1), {upper_seconds: time, last_source_pts_seconds: pts, frames: segments.at(-1).frames + 1});
    else segments.push({lower_seconds: time, upper_seconds: time, first_source_pts_seconds: pts, last_source_pts_seconds: pts, frames: 1});
    if (corroboration.length) {
      const segment = segments.at(-1); segment.contextual_frames = (segment.contextual_frames ?? 0) + 1;
      segment.corroborating_updates ??= [];
      for (const update of corroboration) if (!segment.corroborating_updates.some(u => equal(u, update))) segment.corroborating_updates.push(update);
    }
  }
  const supported = segments.filter(s => s.frames >= 2 || s.contextual_frames);
  return {kind: 'sustained_recognition', segments: supported, association_window: [supportStart, end], press_range: null, release_range: null,
    recognition_envelope: supported.length ? [supported[0].lower_seconds, supported.at(-1).upper_seconds] : null,
    note: 'Filled receptor with a long body is hold-state evidence, not repeated presses or a measured switch release.'};
}
export function attach(data: RecordData, frames: RecordData[], holds: RecordData[], geometry: Geometry, requireGeometry = false): RecordData[] {
  const times = frames.map(f => f.playback_seconds), contextual = contextualSupport(data, frames, geometry.receptor, geometry.spacing, holds, requireGeometry);
  return holds.map(h => ({...h, input: recognitionSegments(frames, times, h, contextual, recognitionWindow(data, h, geometry))}));
}
export function sustained(input: RecordData): RecordData {
  return {holds: attach(input.data, input.frames, input.holds, input.geometry, input.require_hold_geometry ?? false), receptor_runs: receptorRuns(input.frames)};
}
export function sustainedCached(input: RecordData, directory: string): RecordData {
  return new Store(directory).run('hold-state', implementation(new URL('./hold_state.ts', import.meta.url)), input, () => sustained(input));
}
export function current(directory: string): boolean {
  const path = resolve(directory, 'hold-state-input.json');
  return existsSync(path) && artifactCurrent(directory, 'hold-state', implementation(new URL('./hold_state.ts', import.meta.url)), parseData(readFileSync(path, 'utf8')));
}
export function receptorRuns(frames: RecordData[]): RecordData[] {
  const runs = [], current = new Map(), known = new Map(), bridge = new Map(), hiddenLight = new Map();
  let previousTime = null;
  for (const frame of frames) {
    const time = frame.playback_seconds, continuous = previousTime == null || 0 < time - previousTime && time - previousTime <= .075;
    frame.receptor_lit.forEach((lit, lane) => {
      if (!continuous) {bridge.set(lane, false); hiddenLight.set(lane, false);}
      const previous = current.get(lane);
      if (previous && previous.lit === lit && continuous) Object.assign(previous, {end_seconds: time, last_source_pts_seconds: frame.source_pts_seconds, frames: previous.frames + 1});
      else {
        const run: RecordData = {lane, lit, start_seconds: time, end_seconds: time, frames: 1, first_source_pts_seconds: frame.source_pts_seconds,
          last_source_pts_seconds: frame.source_pts_seconds, previous_seconds: previous?.end_seconds ?? null, previous_lit: previous?.lit ?? null};
        runs.push(run); current.set(lane, run);
        if (lit === true) {
          const before = known.get(lane); run.onset_range = null;
          if (bridge.get(lane) && before && before.lit === false && time - before.end_seconds <= .15) {
            run.onset_range = [before.end_seconds, time]; run.onset_source_pts_seconds = [before.last_source_pts_seconds, frame.source_pts_seconds];
          }
          if (hiddenLight.get(lane) && before && before.lit === true && 0 < time - before.end_seconds && time - before.end_seconds <= .15) {
            Object.assign(before, {corroborating_lit_frames_after_flash: 1, corroborating_source_pts_seconds: frame.source_pts_seconds, corroborating_playback_seconds: time});
          }
        }
      }
      if (lit == null) {
        bridge.set(lane, Boolean(bridge.get(lane) && frame.common_receptor_flash));
        hiddenLight.set(lane, Boolean(continuous && frame.common_receptor_flash && (hiddenLight.get(lane) || previous?.lit === true)));
      } else {known.set(lane, current.get(lane)); bridge.set(lane, lit === false); hiddenLight.set(lane, false);}
    });
    previousTime = time;
  }
  return runs;
}
