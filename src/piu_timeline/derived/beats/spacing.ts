import {contracts} from '../contracts.ts';
import {equal, median} from '../math.ts';
import {predictions} from './coordinates.ts';
import type {CoordinateSupport, Note, RecordData} from '../types.ts';
const C = contracts.coordinates, S = contracts.spacing, K = contracts.clock_conversion;

export function attributedHeads(a: number, b: number, notes: Note[], models: RecordData[]): [number[], RecordData[]] {
  if (!models.length) return [[a, b], []];
  const rejected = new Set<number>(), proof = [];
  for (const model of models) {
    if (!model.peer_offsets_pixels) return [[a, b], []];
    const errors = [a, b].map((i, j) => model.peer_offsets_pixels[j] - (model.offset_at_origin_pixels + model.velocity_pixels_per_second * (notes[i].target_seconds - model.origin_seconds)));
    const tolerance = C.maximum_reference_error_spacing * model.lane_spacing_pixels + model.maximum_reference_error_pixels;
    const bad = [a, b].filter((i, j) => Math.abs(errors[j]) > tolerance + 1e-6);
    bad.forEach(i => rejected.add(i));
    proof.push({chunk: model.chunk, peer_position_errors_pixels: errors, maximum_position_error_pixels: tolerance, contradicting_notes: bad});
  }
  return [[a, b].filter(i => rejected.has(i)), proof];
}

export function registeredGap(first: Note, second: Note, samples: number[][], offsets: RecordData, frames: RecordData, a: number, b: number): number | null {
  const secondPoints = new Map(second.points), gaps = [];
  const times = first.points.map(p => p[0]).filter(t => secondPoints.has(t) && samples[0][0] <= t && t <= samples.at(-1)[0]).sort((a, b) => a - b);
  for (const t of times) {
    const chunk = frames[t], heads = offsets[chunk];
    if (heads && Object.hasOwn(heads, a) && Object.hasOwn(heads, b)) gaps.push([t, heads[b] - heads[a]]);
  }
  if (gaps.length < 4 || gaps.at(-1)[0] - gaps[0][0] < .065) return null;
  const corrections = [];
  for (const note of [first, second]) {
    const clock = note.motion_clock ?? {};
    if (!['origin', 'velocity', 'intercept'].every(k => Object.hasOwn(clock, k)) || !Object.hasOwn(note, 'motion_target_phase')) return null;
    const original = clock.origin + ((note.clock_target_phase ?? note.motion_target_phase) - clock.intercept) / clock.velocity;
    corrections.push((note.target_seconds - original) * clock.velocity);
  }
  return median(gaps.map(p => p[1])) + corrections[1] - corrections[0];
}

export function clockConversion(first: Note, second: Note): RecordData | null {
  const c = first.motion_clock;
  if (!c || !equal(c, second.motion_clock) || !c.window?.length || [first, second].some(n => !Object.hasOwn(n, 'motion_target_phase'))) return null;
  const original = [first, second].map(n => c.origin + ((n.clock_target_phase ?? n.motion_target_phase) - c.intercept) / c.velocity);
  if (Math.max(...[first, second].map((n, i) => Math.abs(n.target_seconds - original[i]))) < 1e-8) return null;
  const span = c.window[1] - c.window[0];
  if (span < .3 || (c.residual ?? 0) <= 0) return null;
  const velocityError = K.slope_error_residual_multiplier * c.residual / span, gap = Math.abs(second.target_seconds - first.target_seconds);
  return {format: K, source_window_seconds: c.window, velocity_error_pixels_per_second: velocityError, target_gap_seconds: gap, position_error_pixels: gap * velocityError};
}

export function spacingFailures(notes: Note[], spacing: number, motion: RecordData | null = null, support: CoordinateSupport | null = null,
  diagnostics: RecordData[] | null = null, baseline: number[] | null = null, changed: number[] | null = null): RecordData[] {
  const offsets = {}, frames = {}, at = new Map<number, number[][]>(), pairs = new Map<string, number[][]>();
  for (const r of motion?.coordinate_registration?.chunks ?? []) if (r.status === 'fitted') offsets[r.chunk] = Object.fromEntries((r.head_offsets ?? []).map(h => [h.note, h.offset_pixels]));
  for (const s of motion?.samples ?? []) frames[s.time] = s.chunk;
  notes.forEach((n, i) => {
    if (n.status !== 'estimated' || n.fit_method === 'isolated_native_track') return;
    for (const [t, y] of n.points) { if (!at.has(t)) at.set(t, []); at.get(t).push([y, i]); }
  });
  for (const [time, points] of [...at].sort((a, b) => a[0] - b[0])) {
    points.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const neighbors = points.slice(1).map((p, i) => [points[i], p]);
    if (baseline) {
      const base = points.filter(p => baseline.includes(p[1]));
      for (let i = 1; i < base.length; i++) {
        const pair = [base[i - 1], base[i]];
        if (!neighbors.some(p => equal(p, pair))) neighbors.push(pair);
      }
    }
    for (const [[ya, a], [yb, b]] of neighbors) if (yb - ya > S.minimum_gap_spacing * spacing) {
      const key = `${a},${b}`;
      if (!pairs.has(key)) pairs.set(key, []);
      pairs.get(key).push([time, yb - ya]);
    }
  }
  const failed = [];
  for (const [key, samples] of pairs) {
    const [a, b] = key.split(',').map(Number);
    if (changed && !changed.includes(a) && !changed.includes(b)) continue;
    if (samples.length < 4 || samples.at(-1)[0] - samples[0][0] < .065) continue;
    const first = notes[a], second = notes[b], ca = first.motion_clock, cb = second.motion_clock;
    const gaps = samples.map(s => s[1]), gap = median(gaps), scatter = median(gaps.map(g => Math.abs(g - gap)));
    if (scatter > C.maximum_native_error_spacing * spacing) continue;
    let predicted = motion === null ? (ca && cb && Object.keys(ca).length && Object.keys(cb).length && equal(ca, cb) ? (second.target_seconds - first.target_seconds) * ca.velocity : null) :
      (ca && cb ? registeredGap(first, second, samples, offsets, frames, a, b) : null);
    const models = predictions(a, b, notes, [samples[0][0], samples.at(-1)[0]], support);
    let comparisonGap = gap;
    if (models.length) {
      const measured = m => m.peer_offsets_pixels[1] - m.peer_offsets_pixels[0];
      const selected = models.reduce((best, m) => Math.abs(m.predicted_gap_pixels - measured(m)) > Math.abs(best.predicted_gap_pixels - measured(best)) ? m : best);
      predicted = selected.predicted_gap_pixels; comparisonGap = measured(selected);
      diagnostics?.push({peer_notes: [a, b], observed_gap_pixels: gap, comparison_gap_pixels: comparisonGap, comparison_basis: 'independent_registered_offsets', models});
    } else if (!ca || !cb) continue;
    const tolerance = Math.max(C.maximum_reference_error_spacing * spacing, 3 * scatter);
    const conversion = motion !== null && predicted !== null && !models.length ? clockConversion(first, second) : null;
    const comparison = tolerance + (conversion?.position_error_pixels ?? 0);
    if (conversion) diagnostics?.push({peer_notes: [a, b], observed_gap_pixels: gap, reconstructed_gap_pixels: predicted, clock_conversion: conversion});
    const [rejected, attribution] = attributedHeads(a, b, notes, models);
    // Independent references constrain each coordinate. A difference of two
    // bounded measurements cannot reuse a single-coordinate error budget, and
    // a correct difference alone cannot validate two equally shifted heads.
    if (models.length ? !rejected.length : predicted !== null && Math.abs(predicted - comparisonGap) <= comparison + 1e-6) continue;
    for (const i of rejected) failed.push({note: i, lane: notes[i].lane, reason: predicted !== null ? 'shared_spacing_reconstruction_conflict' : 'shared_spacing_model_unavailable',
      check: 'timing_reconstruction', visible_start_seconds: samples[0][0], visible_end_seconds: samples.at(-1)[0], observed_points: samples.length,
      peer_notes: [a, b], observed_gap_pixels: gap, reconstructed_gap_pixels: predicted,
      ...(models.length ? {comparison_gap_pixels: comparisonGap, comparison_basis: 'independent_registered_offsets'} : {}), tolerance_pixels: tolerance,
      ...(conversion ? {clock_conversion: conversion, comparison_tolerance_pixels: comparison} : {}),
      ...(models.length ? {independent_coordinate_models: models, native_position_attribution: attribution} : {})});
  }
  return failed;
}
