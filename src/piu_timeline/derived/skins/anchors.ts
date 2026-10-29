/** Compare source-bound reference witnesses on the same acquired cap; never calibrate timing. */
import {median} from '../math.ts';
interface Template {id: string; cap_features?: string[]; regions: {name: string; maximum_error?: number}[]}
interface Pattern {template: string; y: number; role: string; classification_status?: string; region_errors: Record<string, number>}
interface Image extends Pattern {lane: number; alternatives?: Pattern[]}
interface Frame {playback_seconds: number; source_pts_seconds: number; observations: Image[]}
interface Sample {
  time: number; source_pts_seconds: number; lane: number; observation_index: number;
  coordinate_pixels: number[]; delta_pixels: number; normalized_cap_errors: number[];
}
export function compare(frames: Frame[], height: number, templates: Template[]) {
  if (!frames.length) throw Error('Anchor-pair review requires native observations');
  if (!Number.isFinite(height) || height <= 0) throw Error('Invalid image height');
  const limits = new Map(templates.filter(t => t.regions.some(r => r.name === 'cap')).map(t => {
    const required = new Set(['cap', ...t.cap_features ?? []]);
    return [t.id, t.regions.filter(r => required.has(r.name)).map(r => [r.name, r.maximum_error ?? .015] as const)];
  }));
  const pairs = new Map<string, {templates: string[]; samples: Sample[]}>();
  let previous: Frame;
  for (const frame of frames) {
    const time = frame.playback_seconds, pts = frame.source_pts_seconds;
    if (![time, pts].every(Number.isFinite) || previous &&
      (time <= previous.playback_seconds || pts <= previous.source_pts_seconds)) throw Error('Invalid native anchor-pair timeline');
    previous = frame;
    frame.observations.forEach((image, index) => {
      if (image.role === 'hold_body' || image.classification_status === 'conflict') return;
      const best = new Map<string, {pattern: Pattern; score: number}>();
      for (const pattern of [image, ...image.alternatives ?? []]) {
        if (!Number.isFinite(pattern.y) || pattern.classification_status === 'conflict') continue;
        const required = limits.get(pattern.template);
        if (!required) continue;
        const errors = required.map(([name, limit]) => {
          const error = pattern.region_errors?.[name];
          return typeof error === 'number' && Number.isFinite(error) && error >= 0 ? Math.fround(error / Math.fround(limit)) : Infinity;
        });
        const score = Math.max(...errors);
        if (score > 1) continue;
        if (!best.has(pattern.template) || score < best.get(pattern.template).score) best.set(pattern.template, {pattern, score});
      }
      const names = [...best.keys()].sort();
      for (let a = 0; a < names.length; a++) for (let b = a + 1; b < names.length; b++) {
        const ids = [names[a], names[b]], key = JSON.stringify(ids);
        if (!pairs.has(key)) pairs.set(key, {templates: ids, samples: []});
        const rows = ids.map(id => best.get(id).pattern.y * height);
        pairs.get(key).samples.push({time, source_pts_seconds: pts, lane: image.lane,
          observation_index: index, coordinate_pixels: rows, delta_pixels: rows[1] - rows[0],
          normalized_cap_errors: ids.map(id => best.get(id).score)});
      }
    });
  }
  return {schema: 1, method: 'same_cap_reference_witness_differences',
    scope: 'relative image anchors only; no absolute timing or automatic correction',
    pairs: [...pairs.values()].map(pair => {
      const deltas = pair.samples.map(s => s.delta_pixels);
      return {...pair, observations: deltas.length, median_delta_pixels: median(deltas),
        delta_range_pixels: [Math.min(...deltas), Math.max(...deltas)]};
    })};
}
