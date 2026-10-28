/** Joint affine constraints; no reference is discarded or moved to a beat row. */
import type {CoordinateModel, Interval, Reference} from '../types.ts';

export type Vertex = [number, number]; // velocity, intercept at the model origin

export function clip(vertices: Vertex[], time: number, offset: number, error: number): Vertex[] {
  let result = vertices;
  for (const sign of [-1, 1]) {
    const input = result; result = [];
    for (let i = 0; i < input.length; i++) {
      const a = input[i], b = input[(i + 1) % input.length];
      const fa = error - sign * (a[1] + a[0] * time - offset), fb = error - sign * (b[1] + b[0] * time - offset);
      if (fa >= -1e-9) result.push(a);
      if ((fa >= -1e-9) !== (fb >= -1e-9)) {
        const fraction = fa / (fa - fb);
        result.push([a[0] + fraction * (b[0] - a[0]), a[1] + fraction * (b[1] - a[1])]);
      }
    }
  }
  return result;
}

export function domain(references: Reference[], origin: number, error: number): Vertex[] {
  const times = references.map(r => r.target_seconds - origin), values = references.map(r => r.offset);
  let lower = -Infinity, upper = Infinity;
  for (let i = 0; i < times.length; i++) for (let j = i + 1; j < times.length; j++) {
    const dt = times[j] - times[i], dy = values[j] - values[i];
    if (!dt) { if (Math.abs(dy) > 2 * error + 1e-9) return []; continue; }
    const a = (dy - 2 * error) / dt, b = (dy + 2 * error) / dt;
    lower = Math.max(lower, Math.min(a, b)); upper = Math.min(upper, Math.max(a, b));
  }
  if (!(0 < lower && lower <= upper + 1e-9 && Number.isFinite(upper))) return [];
  if (lower > upper) lower = upper = (lower + upper) / 2;
  // Work near zero so a large registered phase origin does not lose precision.
  const base = values[times.indexOf(0)];
  let vertices: Vertex[] = [[lower, -error], [upper, -error], [upper, error], [lower, error]];
  for (let i = 0; i < times.length && vertices.length; i++) vertices = clip(vertices, times[i], values[i] - base, error);
  return vertices.map(([v, b]) => [v, b + base]);
}

export function targetRange(model: CoordinateModel, offset: number, error: number): Interval {
  const vertices = model.coordinate_domain?.vertices;
  if (!vertices?.length || vertices.some(([v,b]) => !Number.isFinite(v) || v <= 0 || !Number.isFinite(b)) ||
    !Number.isFinite(offset) || !Number.isFinite(error) || error < 0) throw new Error('Bounded positive coordinate model is required');
  const lower = vertices.map(([v, b]) => model.origin_seconds + (offset - error - b) / v);
  const upper = vertices.map(([v, b]) => model.origin_seconds + (offset + error - b) / v);
  return [Math.min(...lower), Math.max(...upper)];
}
