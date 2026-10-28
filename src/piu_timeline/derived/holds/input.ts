/** Native image geometry survives a failed musical-row assignment. */
import type {RecordData, Interval} from '../types.ts';
const beatFailures = new Set(['beat_timing_reconstruction_failed', 'beat_grid_conflicts_with_spatial_spacing', 'beat_grid_conflicts_with_native_chord']);
export function nativeRange(note: RecordData): Interval | null {
  const range = note.video_target_range;
  return note.timing_reconstruction?.status === 'restored' && Array.isArray(range) && range.length === 2 &&
    range.every(Number.isFinite) && range[0] < range[1] ? [range[0], range[1]] : null;
}
export function inputNotes(notes: RecordData[]): RecordData[] {
  return notes.map(note => {
    const range = nativeRange(note);
    if (!range || note.status !== 'excluded' || !beatFailures.has(note.reason) || note.beat_reconstruction?.status !== 'failed') return note;
    return {...note, status: 'estimated', reason: null, target_seconds: (range[0] + range[1]) / 2,
      prediction_uncertainty_seconds: (range[1] - range[0]) / 2, geometry_native_range: range,
      geometry_source_failure: {reason: note.reason, beat_reconstruction: note.beat_reconstruction}};
  });
}
export function nativeHead(h: RecordData, index: number, note: RecordData): boolean {
  const range = nativeRange(note);
  return !!range && (h.geometry_native_endpoint_notes ?? []).includes(index) && range.every((value, i) => value === h.start_range[i]);
}
