/** Project independently measured cap centers; preserve unmatched detections. */
import type {RecordData} from '../types.ts';
export function project(raw: number[][], record: RecordData): number[][] {
  const samples = new Map(record.observations.map(s => [s.time, s]));
  if (samples.size !== record.observations.length) throw Error('Duplicate native cap measurements');
  const fallback = record.status === 'registered' ? record.offset_pixels : 0;
  const times = new Set(raw.map(([t]) => t));
  if ([...samples.keys()].some(t => !times.has(t as number))) throw Error('Native cap measurement has no original frame');
  return raw.map(([time, y]) => {
    const sample = samples.get(time) as RecordData;
    if (sample && Math.abs(sample.detected_y_pixels - y) > 1e-5) throw Error('Native cap measurement differs from original detection');
    const offset = sample ? sample.offset_pixels : fallback;
    if (![time, y, offset].every(Number.isFinite)) throw Error('Nonfinite native cap projection');
    return [time, y + offset];
  });
}
