import {contracts} from '../contracts.ts';
import {entries} from '../math.ts';
import {fit} from './coordinates.ts';
import type {Interval, RecordData} from '../types.ts';
const F = contracts.coordinates;

export function constrain(options: Interval[], step: number, origin: number, blocks: RecordData[]): [Interval[], RecordData[]] {
  const result = options.map(v => [...v] as Interval), proofs = [];
  options.forEach(([lo, hi], index) => {
    if (lo > hi) return;
    for (const block of blocks) {
      const heads = block.heads;
      if (!Object.hasOwn(heads, index)) continue;
      const radius = F.reference_radius_seconds;
      const window = block.reference_window ?? [origin + lo * step - radius, origin + hi * step + radius];
      const refs = (block.references ?? []).filter(r => window[0] <= r.target_seconds && r.target_seconds <= window[1]).map(r => ({...r}));
      for (const [peer, head] of entries<RecordData>(heads)) {
        const [a, b] = options[peer];
        if (peer === index || a !== b || block.neighbors_only) continue;
        const target = origin + a * step;
        if (origin + lo * step - radius <= target && target <= origin + hi * step + radius) refs.push({note: head.native_note ?? peer, target_seconds: target, ...head});
      }
      const model = fit(refs, block.lane_spacing_pixels);
      if (!model) continue;
      const [lower, upper] = model.reference_target_range;
      if (!(lower <= origin + lo * step && origin + hi * step <= upper)) continue;
      const error = F.maximum_native_error_spacing * model.lane_spacing_pixels + model.maximum_reference_error_pixels;
      const velocity = model.velocity_pixels_per_second, offset = heads[index].offset;
      const time = model.origin_seconds + (offset - model.offset_at_origin_pixels) / velocity;
      const allowed: Interval = [Math.max(lo, Math.ceil((Math.max(lower, time - error / velocity) - origin) / step - 1e-8)),
        Math.min(hi, Math.floor((Math.min(upper, time + error / velocity) - origin) / step + 1e-8))];
      const before = result[index];
      result[index] = [Math.max(before[0], allowed[0]), Math.min(before[1], allowed[1])];
      proofs.push({index, note: heads[index].native_note ?? index, chunk: block.chunk, original_domain: [lo, hi],
        allowed_domain: allowed, measured_offset_pixels: offset, maximum_position_error_pixels: error, model});
    }
  });
  return [result, proofs];
}
