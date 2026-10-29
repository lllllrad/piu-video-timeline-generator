/** Adjacent captured-frame motion from measured coordinates, independent of cap type. */
import type {Trajectory} from '../coordinates/points.ts';
import {median} from '../math.ts';
interface Note {motion_trajectory:Trajectory<'fit'>; duplicate_of?: number | null}
interface Sample {time: number; chunk: number; support: number; phase: number; coordinate_status?: string}
interface Frame {time: number; source_pts: number}
export interface Step {
  time: number; method: string; displacement_pixels: number;
  source_pts_range: [number, number]; source_notes?: number[];
}
export function steps(notes: Note[], samples: Sample[], timeline: Frame[], spacing: number): Step[] {
  if (!Number.isFinite(spacing) || spacing <= 0) throw Error('Invalid cap spacing');
  const positions = new Map<number, Map<number, number>>();
  notes.forEach((note, i) => {
    if (note.duplicate_of != null) return;
    const fit=note.motion_trajectory;
    if(fit?.purpose!=='fit'||fit.frame!=='analysis_image_pixels'||fit.vertical_axis!=='down'||!Array.isArray(fit.points))
      throw new Error('Image motion requires a fit trajectory in analysis pixels');
    for (const [time, y] of fit.points) {
      if (![time, y].every(Number.isFinite)) throw Error('Invalid measured cap coordinate');
      if (!positions.has(time)) positions.set(time, new Map());
      positions.get(time).set(i, y);
    }
  });
  const motion = new Map(samples.map(s => [s.time, s])), result: Step[] = [];
  for (let i = 0; i < timeline.length; i++) {
    const after = timeline[i], before = timeline[i - 1];
    if (![after.time, after.source_pts].every(Number.isFinite) || before &&
      (after.time <= before.time || after.source_pts <= before.source_pts)) throw Error('Invalid native motion timeline');
    if (!before) continue;
    const dt = after.time - before.time;
    if (dt > .05 + 1e-6) continue;
    const a = motion.get(before.time), b = motion.get(after.time);
    if (a?.coordinate_status === 'failed' || b?.coordinate_status === 'failed') continue;
    let value: number, method: string, source_notes: number[] | undefined;
    if (a && b && a.chunk === b.chunk && b.support) {
      value = b.phase - a.phase; method = 'registered_frame_displacement';
    } else {
      const first = positions.get(before.time), last = positions.get(after.time);
      const peers = [...last ?? []].filter(([id]) => first?.has(id));
      const deltas = peers.map(([id, y]) => first.get(id) - y);
      if (!deltas.length || Math.max(...deltas) - Math.min(...deltas) > 1) continue;
      value = median(deltas); method = 'identified_cap_displacement'; source_notes = peers.map(([id]) => id);
    }
    if (!Number.isFinite(value) || value < -.75 || value > 30 * spacing * dt) continue;
    result.push({time: after.time, method, displacement_pixels: value,
      source_pts_range: [before.source_pts, after.source_pts], ...(source_notes ? {source_notes} : {})});
  }
  return result;
}
