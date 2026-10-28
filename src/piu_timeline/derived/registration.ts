/** Joint head/frame coordinate registration on measured positions. */
import {contracts} from './contracts.ts';
import {maximum, mean, rms, sum} from './math.ts';
import type {RecordData} from './types.ts';
const F = contracts.registration;
const dot = (a: number[], b: number[]) => sum(a.map((v, i) => v * b[i]));

export function solve(head: number[], frame: number[], y: number[], initial: number[], headCount: number, frameCount: number): unknown[] {
  if (!y.every(Number.isFinite)) throw new Error('nonfinite_registered_positions');
  let weights = y.map(() => 1), offsets: number[] | null = null, iterations = 0, phase = [];
  for (let pass = 0; pass < F.robust_passes; pass++) {
    const degree = Array(headCount).fill(0), total = Array(frameCount).fill(0), meanY = Array(frameCount).fill(0);
    y.forEach((v, i) => { degree[head[i]] += weights[i]; total[frame[i]] += weights[i]; meanY[frame[i]] += weights[i] * v; });
    if ([...degree, ...total].some(v => v <= 0)) throw new Error('unobserved_joint_coordinate');
    meanY.forEach((v, i) => meanY[i] = v / total[i]);
    const rhs = Array(headCount).fill(0), diagonal = [...degree];
    y.forEach((v, i) => { rhs[head[i]] += weights[i] * (v - meanY[frame[i]]); diagonal[head[i]] -= weights[i] ** 2 / total[frame[i]]; });
    const rhsMean = mean(rhs); rhs.forEach((v, i) => rhs[i] = v - rhsMean);
    const product = (values: number[]) => {
      const means = Array(frameCount).fill(0), result = degree.map((v, i) => v * values[i]);
      y.forEach((_, i) => means[frame[i]] += weights[i] * values[head[i]]);
      means.forEach((v, i) => means[i] = v / total[i]);
      y.forEach((_, i) => result[head[i]] -= weights[i] * means[frame[i]]);
      return result;
    };
    if (!offsets) {
      offsets = Array(headCount).fill(0);
      y.forEach((v, i) => offsets[head[i]] += weights[i] * (v + initial[frame[i]]));
      offsets = offsets.map((v, i) => v / degree[i]);
    }
    const offsetMean = mean(offsets); offsets = offsets.map(v => v - offsetMean);
    const projected = product(offsets), residual = rhs.map((v, i) => v - projected[i]);
    let scaled = residual.map((v, i) => v / Math.max(diagonal[i], 1e-9)), direction = [...scaled], error = dot(residual, scaled);
    for (let it = 0; it < F.maximum_iterations; it++) {
      if (Math.sqrt(Math.max(0, error)) < F.gradient_tolerance) break;
      const projected = product(direction), denominator = dot(direction, projected);
      if (denominator <= 1e-20) break;
      const step = error / denominator;
      offsets.forEach((v, i) => { offsets[i] = v + step * direction[i]; residual[i] -= step * projected[i]; });
      scaled = residual.map((v, i) => v / Math.max(diagonal[i], 1e-9));
      const updated = dot(residual, scaled);
      direction = scaled.map((v, i) => v + updated / error * direction[i]); error = updated; iterations++;
    }
    if (!offsets.every(Number.isFinite) || Math.sqrt(Math.max(0, error)) >= F.gradient_tolerance) throw new Error('joint_coordinate_solver_not_converged');
    phase = Array(frameCount).fill(0);
    y.forEach((v, i) => phase[frame[i]] += weights[i] * (offsets[head[i]] - v));
    phase = phase.map((v, i) => v / total[i]);
    weights = y.map((v, i) => Math.min(1, F.huber_pixels / Math.max(Math.abs(offsets[head[i]] - phase[frame[i]] - v), 1e-6)));
  }
  const origin = phase[0];
  return [phase.map(v => v - origin), offsets.map(v => v - origin), iterations];
}

export function refine(samples: RecordData[], tracks: RecordData[], receptor: number, spacing: number, bottom: number): RecordData {
  samples = samples.map(s => ({...s}));
  const positions = new Map<number, Map<number, number>>(), chunks = new Map<number, RecordData[]>();
  tracks.forEach((track, i) => { for (const [t, y] of track.points) if (receptor + .85 * spacing < y && y < bottom - .55 * spacing) {
    if (!positions.has(t)) positions.set(t, new Map()); positions.get(t).set(i, y);
  } });
  for (const s of samples) { if (!chunks.has(s.chunk)) chunks.set(s.chunk, []); chunks.get(s.chunk).push(s); }
  const failures = {}, conflicts = [], offsets = [], diagnostics = [];
  for (const [number, chunk] of chunks) {
    if (chunk.length < 4) continue;
    const identities = [...new Set(chunk.flatMap(s => [...(positions.get(s.time)?.keys() ?? [])]))].sort((a, b) => a - b);
    if (identities.length < 2) continue;
    const mapping = new Map(identities.map((id, i) => [id, i])), heads = [], frames = [], ys = [], parents = identities.map((_, i) => i);
    const root = (i: number) => { while (parents[i] !== i) { parents[i] = parents[parents[i]]; i = parents[i]; } return i; };
    chunk.forEach((s, frame) => {
      const indices = [...(positions.get(s.time)?.keys() ?? [])];
      for (const index of indices) { heads.push(mapping.get(index)); frames.push(frame); ys.push(positions.get(s.time).get(index)); parents[root(mapping.get(index))] = root(mapping.get(indices[0])); }
    });
    const record: RecordData = {chunk: number, frames: chunk.length, heads: identities.length, source_pts_seconds: [chunk[0].source_pts, chunk.at(-1).source_pts]};
    try {
      if (new Set(identities.map((_, i) => root(i))).size !== 1) throw new Error('disconnected_registered_identities');
      const [phase, fitted, iterations] = solve(heads, frames, ys, chunk.map(s => s.phase), identities.length, chunk.length) as [number[], number[], number];
      let runningMaximum = -Infinity;
      const forward = phase.map(v => runningMaximum = Math.max(runningMaximum, v));
      if (maximum(forward.map((v, i) => v - phase[i])) > Math.max(.75, .02 * spacing)) throw new Error('joint_coordinates_contradict_forward_motion');
      const errors = ys.map((v, i) => fitted[heads[i]] - forward[frames[i]] - v);
      Object.assign(record, {status: 'fitted', iterations, residual_pixels: rms(errors), maximum_residual_pixels: maximum(errors.map(Math.abs)),
        maximum_forward_adjustment_pixels: maximum(forward.map((v, i) => v - phase[i])), maximum_phase_correction_pixels: maximum(forward.map((v, i) => Math.abs(v - chunk[i].phase))),
        head_offsets: identities.map((id, i) => ({note: id, offset_pixels: fitted[i]}))});
      identities.forEach((id, i) => offsets.push([id, number, fitted[i]]));
      chunk.forEach((s, i) => Object.assign(s, {phase: forward[i], coordinate_status: 'joint_registered'}));
      identities.forEach((id, local) => {
        const bad = heads.flatMap((h, i) => h === local && Math.abs(errors[i]) > .15 * spacing ? [i] : []);
        if (!bad.length) return;
        const times = bad.map(i => chunk[frames[i]].time);
        conflicts.push({note: id, lane: tracks[id].lane, reason: 'shared_motion_observation_conflict', check: 'timing_reconstruction', visible_start_seconds: Math.min(...times), visible_end_seconds: Math.max(...times),
          source_pts_seconds: [chunk[frames[bad[0]]].source_pts, chunk[frames[bad.at(-1)]].source_pts], observed_points: bad.length,
          maximum_position_error_pixels: Math.max(...bad.map(i => Math.abs(errors[i]))), position_tolerance_pixels: .15 * spacing, motion_chunk: number});
      });
    } catch (error) {
      if (!['disconnected_registered_identities', 'nonfinite_registered_positions', 'unobserved_joint_coordinate',
        'joint_coordinate_solver_not_converged', 'joint_coordinates_contradict_forward_motion'].includes(error.message)) throw error;
      Object.assign(record, {status: 'failed', reason: error.message}); failures[number] = error.message;
      chunk.forEach(s => s.coordinate_status = 'failed');
    }
    diagnostics.push(record);
  }
  return {samples, coordinate_failures: failures, coordinate_conflicts: conflicts, coordinate_offsets: offsets, coordinate_registration: {format: F, chunks: diagnostics}};
}
