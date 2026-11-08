/** Project measured centers without introducing unmatched image origins into a fit. */
import type {RecordData} from '../types.ts';
export function project(raw: number[][], record: RecordData, mode:'all_frames'|'measured_frames'='all_frames'): number[][] {
  if(!['all_frames','measured_frames'].includes(mode))throw Error('Unknown cap projection mode');
  const samples = new Map(record.observations.map(s => [s.time, s]));
  if (samples.size !== record.observations.length) throw Error('Duplicate native cap measurements');
  const fallback = record.status === 'registered' ? record.offset_pixels : 0;
  const times = new Set(raw.map(([t]) => t));
  if ([...samples.keys()].some(t => !times.has(t as number))) throw Error('Native cap measurement has no original frame');
  const selected=mode==='measured_frames'?raw.filter(([time])=>samples.has(time)):raw;
  return selected.map(([time, y]) => {
    const sample = samples.get(time) as RecordData;
    if (sample && Math.abs(sample.detected_y_pixels - y) > 1e-5) throw Error('Native cap measurement differs from original detection');
    const offset = sample ? sample.offset_pixels : fallback;
    if (![time, y, offset].every(Number.isFinite)) throw Error('Nonfinite native cap projection');
    return [time, y + offset];
  });
}

/** One transport exchange for a complete coordinate stage. */
export function projectMany(requests:[number[][],RecordData|null,'all_frames'|'measured_frames'][]):number[][][]{
 return requests.map(([raw,record,mode])=>record?project(raw,record,mode):structuredClone(raw));
}
