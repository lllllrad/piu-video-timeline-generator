import {contracts, RECOVERABLE} from '../contracts.ts';
import {entries, median} from '../math.ts';
import type {CoordinateModel, CoordinateSupport, Interval, Note, RecordData, Reference} from '../types.ts';
const F = contracts.coordinates;

export function prepare(data: RecordData, spacing: number, includeFailed = false): CoordinateSupport | null {
  const motion = data.scroll_motion ?? {}, samples = new Map<number, RecordData>((motion.samples ?? []).map(s => [s.time, s]));
  const observed: Record<string, number[]> = {};
  for (const r of data.head_registration?.notes ?? []) {
    if (r.status === 'registered' || ['native_cap_measurements', 'native_image_anchors'].includes(r.coordinate_method)) {
      observed[r.note] = r.observations.filter(s => s.native_cap_registration_status !== 'conflicting').map(s => s.time);
    }
  }
  if (!Object.keys(observed).length) return null;
  const height = data.analysis_height, receptor = data.layout.receptor_y * height;
  const bottom = (data.layout.note_y_max ?? .95) * height, chunks = {};
  for (const record of motion.coordinate_registration?.chunks ?? []) {
    if (record.status !== 'fitted') continue;
    const heads = {};
    for (const head of record.head_offsets) {
      const i = head.note, note = data.notes[i];
      if (!observed[i]) continue;
      if (note.status !== 'estimated' && !(includeFailed && [...RECOVERABLE, 'beat_timing_reconstruction_failed',
        'beat_grid_conflicts_with_spatial_spacing', 'beat_grid_conflicts_with_native_chord'].includes(note.reason))) continue;
      const times = new Set(observed[i]);
      const points = note.points.filter(([t, y]) => times.has(t) && samples.has(t) && samples.get(t).chunk === record.chunk &&
        receptor + .85 * spacing < y && y < bottom - .55 * spacing);
      if (points.length < 4 || points.at(-1)[0] - points[0][0] < .065) continue;
      const error = Math.max(...points.map(([t, y]) => Math.abs(y + samples.get(t).phase - head.offset_pixels)));
      if (error > F.maximum_native_error_spacing * spacing) continue;
      heads[i] = {offset: head.offset_pixels, lane: note.lane, native_points: points.length,
        native_maximum_error_pixels: error, source_pts_range: [samples.get(points[0][0]).source_pts, samples.get(points.at(-1)[0]).source_pts]};
    }
    chunks[record.chunk] = heads;
  }
  return {lane_spacing_pixels: spacing, chunks, frames: Object.fromEntries([...samples].map(([t, s]) => [t, s.chunk])),
    observed, reference_notes: data.notes.flatMap((n, i) => n.status === 'estimated' ? [i] : [])};
}

export function fit(references: Reference[], spacing: number): CoordinateModel | null {
  if (!Number.isFinite(spacing) || spacing <= 0) throw new Error('Native coordinate fitting requires positive lane spacing');
  if (references.length < F.minimum_references || new Set(references.map(r => r.lane)).size < F.minimum_lanes) return null;
  const targets = references.map(r => r.target_seconds), offsets = references.map(r => r.offset);
  const origin = Math.min(...targets), end = Math.max(...targets);
  if (new Set(targets).size < 3 || end - origin < F.minimum_target_span_seconds) return null;
  const slopes: number[] = [];
  for (let i = 0; i < targets.length; i++) for (let j = i + 1; j < targets.length; j++) {
    if (Math.abs(targets[j] - targets[i]) >= F.minimum_slope_span_seconds) slopes.push((offsets[j] - offsets[i]) / (targets[j] - targets[i]));
  }
  if (!slopes.length) return null;
  const velocity = median(slopes), intercept = median(offsets.map((v, i) => v - velocity * (targets[i] - origin)));
  const error = Math.max(...offsets.map((v, i) => Math.abs(v - velocity * (targets[i] - origin) - intercept)));
  if (velocity <= 0 || error > F.maximum_reference_error_spacing * spacing) return null;
  return {lane_spacing_pixels: spacing, velocity_pixels_per_second: velocity, origin_seconds: origin,
    offset_at_origin_pixels: intercept, maximum_reference_error_pixels: error,
    reference_target_range: [origin, end], references};
}

export function predictions(a: number, b: number, notes: Note[], interval: Interval, support: CoordinateSupport | null, radius = F.reference_radius_seconds): RecordData[] {
  if (!support) return [];
  const ta = notes[a].target_seconds, tb = notes[b].target_seconds;
  const bp = new Set(notes[b].points.map(p => p[0])), ao = new Set(support.observed[a] ?? []), bo = new Set(support.observed[b] ?? []);
  const common = notes[a].points.map(p => p[0]).filter(t => bp.has(t) && ao.has(t) && bo.has(t));
  const models = [], eligible = new Set(support.reference_notes);
  for (const [number, heads] of entries(support.chunks)) {
    if (!heads[a] || !heads[b]) continue;
    const times = common.filter(t => interval[0] <= t && t <= interval[1] && support.frames[t] === number).sort((a, b) => a - b);
    if (times.length < 4 || times.at(-1) - times[0] < .065) continue;
    const refs = entries(heads).filter(([i]) => i !== a && i !== b && eligible.has(i) && notes[i].status === 'estimated' &&
      Math.min(ta, tb) - radius <= notes[i].target_seconds && notes[i].target_seconds <= Math.max(ta, tb) + radius)
      .map(([i, h]) => ({note: i, target_seconds: notes[i].target_seconds, ...h}));
    const sets = [refs];
    for (const proof of support.recovery_reference_sets ?? []) {
      if (proof.chunk !== number || ![a, b].includes(proof.note)) continue;
      if (proof.references.some(r => !eligible.has(r.note) || notes[r.note].status !== 'estimated' || notes[r.note].target_seconds !== r.target_seconds)) continue;
      sets.push(proof.references.filter(r => ![a, b].includes(r.note)));
    }
    const seen = new Set();
    for (const refs of sets) {
      const key = refs.map(r => r.note).sort((a, b) => a - b).join(',');
      if (seen.has(key)) continue;
      seen.add(key);
      const model = fit(refs, support.lane_spacing_pixels);
      if (!model) continue;
      const [lo, hi] = model.reference_target_range;
      if (!(lo <= Math.min(ta, tb) && Math.max(ta, tb) <= hi)) continue;
      models.push({chunk: number, predicted_gap_pixels: model.velocity_pixels_per_second * (tb - ta),
        peer_offsets_pixels: [heads[a].offset, heads[b].offset], coobserved_points: times.length,
        visible_range: [times[0], times.at(-1)], ...model});
    }
  }
  return models;
}
