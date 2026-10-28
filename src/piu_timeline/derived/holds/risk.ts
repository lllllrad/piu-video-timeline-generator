/** Bound future receptor contact from native endpoint ranges and measured speed. */
import {nativeEndpoint, inputNotes} from './input.ts';
import type {RecordData} from '../types.ts';

export function capGuard(input: RecordData): number | null {
  const h = input.hold, notes = input.notes, spacing = input.spacing, cadence = input.cadence, extent = input.extent_spacing;
  if (h.head_note == null || h.tail_note == null || h.head_note === h.tail_note ||
    h.start_censored !== false || h.end_censored !== false || !h.end_range ||
    !Number.isFinite(h.body_frames) || h.body_frames < 4 ||
    !['skin_start_body_end_images', 'skin_temporal_image_regions'].includes(h.body_evidence) ||
    ![spacing, cadence, extent].every(v => typeof v === 'number' && Number.isFinite(v) && v > 0) || notes.length !== 2) return null;
  const speeds: number[] = [];
  for (const [i, edge] of (['start', 'end'] as const).entries()) {
    const note = notes[i], index = i === 0 ? h.head_note : h.tail_note;
    if (note.timing_reconstruction?.status === 'failed') return null;
    if (note.beat_reconstruction?.status === 'failed') {
      if (inputNotes([note])[0].status !== 'estimated' || !nativeEndpoint(h, index, note, edge)) return null;
    } else if (note.status !== 'estimated') return null;
    const measured = [note.velocity_pixels_per_second, note.motion_clock?.velocity]
      .filter(v => typeof v === 'number' && Number.isFinite(v) && Math.abs(v) > 0).map(Math.abs);
    if (!measured.length) return null;
    speeds.push(...measured);
  }
  return Math.max(2 * cadence, extent * spacing / Math.min(...speeds));
}
