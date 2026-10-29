import {contracts} from '../contracts.ts';
import {equal, linear} from '../math.ts';
import type {Interval, Note, RecordData} from '../types.ts';
const F = contracts.chords, A = F.native_cap_registration;

export function prepare(data: RecordData, spacing: number): RecordData[] {
  const at = new Map<number, RecordData[]>();
  for (const record of data.head_registration?.notes ?? []) {
    const image = record.coordinate_method === 'native_image_anchors';
    if (!image && (record.coordinate_method !== 'native_cap_measurements' ||
      (record.coordinate_uncertainty_pixels ?? Infinity) > F.coordinate_error_spacing * spacing)) continue;
    const index = record.note, note = data.notes[index], points = new Map<number, number>(note.points);
    for (const sample of record.observations) {
      if (image && sample.native_cap_registration_status === 'conflicting') continue;
      const time = sample.time;
      if (!points.has(time)) continue;
      let model = ['calibrated', null], endpointError = 0;
      if (image) {
        if (!sample.template || Math.abs(sample.native_y_pixels - points.get(time)) > 1e-5) {
          throw new Error('Image chord coordinates disagree with native reference anchors');
        }
        const uncertainty = sample.native_cap_coordinate_uncertainty_pixels;
        if (uncertainty != null) {
          const scale = sample.native_cap_reference_scale_y;
          if (!equal(data.head_registration?.format?.native_cap_registration, A) ||
            [uncertainty, scale].some(v => typeof v !== 'number' || !Number.isFinite(v) || v <= 0) ||
            Math.abs(uncertainty - A.coordinate_uncertainty_pixels * scale) > 1e-9) {
            throw new Error('Image chord has an unsupported native anchor registration');
          }
        }
        if (uncertainty != null && uncertainty <= F.coordinate_error_spacing * spacing) endpointError = uncertainty;
        if (uncertainty == null || uncertainty > F.coordinate_error_spacing * spacing) {
          model = sample.cap_reference_sha256 ? ['image_reference', sample.cap_reference_sha256] : ['image_template', sample.template];
        }
      }
      if (!at.has(time)) at.set(time, []);
      at.get(time).push({index, lane: note.lane, y: points.get(time), pts: sample.source_pts_seconds, model, endpointError,
        reference: image ? (sample.native_cap_reference_template ?? sample.template) : null});
    }
  }
  const pairs = new Map<string, RecordData>();
  for (const [time, points] of [...at].sort((a, b) => a[0] - b[0])) {
    if (Math.max(...points.map(p => p.pts)) - Math.min(...points.map(p => p.pts)) > 1e-6) throw new Error('Native cap measurements disagree on source PTS');
    points.sort((a, b) => a.index - b.index || a.lane - b.lane || a.y - b.y);
    for (let i = 0; i < points.length; i++) for (let j = i + 1; j < points.length; j++) {
      const a = points[i], b = points[j];
      if (a.lane === b.lane || Math.abs(a.pts - b.pts) > 1e-6 || !equal(a.model, b.model)) continue;
      const key = JSON.stringify([a.index, b.index, a.model]);
      if (!pairs.has(key)) pairs.set(key, {a: a.index, b: b.index, model: a.model, samples: []});
      pairs.get(key).samples.push([time, a.y, b.y, a.pts, a.reference, b.reference, a.endpointError, b.endpointError]);
    }
  }
  const result = [];
  for (const {a, b, model, samples} of [...pairs.values()].sort((x, y) => x.a - y.a || x.b - y.b || String(x.model).localeCompare(String(y.model)))) {
    if (samples.length < F.minimum_frames || samples.at(-1)[0] - samples[0][0] < F.minimum_span_seconds || new Set(samples.map(s => s[3])).size !== samples.length) continue;
    const gap = Math.max(...samples.map(s => Math.abs(s[1] - s[2])));
    // Only source-certified per-frame image positions supply endpoint intervals.
    // Every co-observed frame must admit one common physical inter-head gap.
    const measuredBounds = samples.every(s => s[6] > 0 && s[7] > 0);
    const gapRange = measuredBounds ? [Math.max(...samples.map(s => s[2] - s[1] - s[6] - s[7])),
      Math.min(...samples.map(s => s[2] - s[1] + s[6] + s[7]))] : null;
    const maximumGap = F.maximum_gap_spacing * spacing;
    if (gapRange ? Math.max(gapRange[0], -maximumGap) > Math.min(gapRange[1], maximumGap) + 1e-9 : gap > maximumGap) continue;
    const time = samples.map(s => s[0] - samples[0][0]), y = samples.map(s => (s[1] + s[2]) / 2);
    const [velocity, intercept] = linear(time, y), error = Math.max(...y.map((v, i) => Math.abs(v - velocity * time[i] - intercept)));
    const displacement = y[0] - y.at(-1);
    if (displacement < F.minimum_displacement_spacing * spacing || error > F.maximum_motion_residual_spacing * spacing) continue;
    const lower = (displacement - 2 * F.coordinate_error_spacing * spacing) / time.at(-1);
    if (lower <= 0) continue;
    const templates = [...new Set(samples.flatMap(s => s.slice(4, 6)).filter(v => v != null))].sort();
    result.push({lane_spacing_pixels: spacing, peer_notes: [a, b], observed_points: samples.length, maximum_gap_pixels: gap,
      ...(gapRange ? {native_gap_range_pixels: gapRange, endpoint_uncertainty_pixels: samples.map(s => s.slice(6, 8))} : {}),
      ...(['image_reference', 'image_template'].includes(model[0]) ? {measurement_basis: 'shared_image_reference', reference_identity: model[1], reference_templates: templates} : {}),
      ...(model[0] === 'calibrated' && templates.length ? {measurement_basis: 'source_bound_native_cap_centers', registered_image_templates: templates} : {}),
      visible_start_seconds: samples[0][0], visible_end_seconds: samples.at(-1)[0], source_pts_seconds: samples.map(s => s[3]),
      minimum_velocity_pixels_per_second: lower, maximum_motion_residual_pixels: error});
  }
  return result;
}

export function constrain(domains: Interval[], step: number, constraints: RecordData[]): [Interval[], RecordData[]] {
  const limitSpacing = F.maximum_gap_spacing + 2 * F.coordinate_error_spacing;
  const edges = constraints.map(p => [p, Math.floor(limitSpacing * p.lane_spacing_pixels / (step * p.minimum_velocity_pixels_per_second) + 1e-9)] as const);
  const result = domains.map(d => [...d] as Interval), used = new Set<number>();
  let changed = true;
  while (changed) {
    changed = false;
    edges.forEach(([proof, limit], index) => {
      const [a, b] = proof.indices, first = result[a], second = result[b];
      let narrowed: Interval[];
      if (first[0] > first[1] || second[0] > second[1]) narrowed = [[1, 0], [1, 0]];
      else {
        narrowed = [[Math.max(first[0], second[0] - limit), Math.min(first[1], second[1] + limit)],
          [Math.max(second[0], first[0] - limit), Math.min(second[1], first[1] + limit)]];
        if (narrowed.some(([lo, hi]) => lo > hi)) narrowed = [[1, 0], [1, 0]];
      }
      if (limit === 0 || !equal(narrowed, [first, second])) used.add(index);
      if (!equal(narrowed, [first, second])) { [result[a], result[b]] = narrowed; changed = true; }
    });
  }
  return [result, edges.flatMap(([p], i) => used.has(i) ? [p] : [])];
}

export function conflicts(notes: Note[], constraints: RecordData[]): RecordData[] {
  const result = [];
  for (const proof of constraints) {
    const threshold = (F.maximum_gap_spacing + 2 * F.coordinate_error_spacing) * proof.lane_spacing_pixels;
    const [a, b] = proof.peer_notes;
    if ([a, b].some(i => notes[i].status !== 'estimated')) continue;
    const distance = Math.abs(notes[a].target_seconds - notes[b].target_seconds) * proof.minimum_velocity_pixels_per_second;
    if (distance <= threshold) continue;
    for (const i of [a, b]) result.push({...proof, note: i, lane: notes[i].lane, check: 'timing_reconstruction',
      reason: 'beat_grid_conflicts_with_native_chord', reconstructed_minimum_gap_pixels: distance, maximum_compatible_gap_pixels: threshold});
  }
  return result;
}
