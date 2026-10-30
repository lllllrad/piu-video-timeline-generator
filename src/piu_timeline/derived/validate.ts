import type {BeatInput} from './beats/reconstruct.ts';
const object = (v: unknown): v is Record<string, any> => v !== null && typeof v === 'object' && !Array.isArray(v);
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const assert = (ok: boolean, message: string) => { if (!ok) throw new Error(message); };

export function validateBeatInput(value: unknown): asserts value is BeatInput {
  assert(object(value) && value.schema === 1, 'Unsupported beat-stage input schema');
  const {data, reference: ref, timing_text: timing} = value as BeatInput;
  assert(object(data) && object(ref), 'Beat stage requires observations and an explicit reference state');
  assert(['available', 'unavailable'].includes(ref.status), 'Invalid beat reference status');
  if (ref.status !== 'available') { assert(typeof ref.reason === 'string', 'Unavailable beat reference requires a reason'); return; }
  assert(typeof timing === 'string', 'Available beat reference requires timing text');
  assert(finite(ref.song_start_seconds) && finite(ref.alignment_uncertainty_seconds) && ref.alignment_uncertainty_seconds >= 0 && ref.alignment_uncertainty_seconds <= .1,
    'Beat reference requires a finite, bounded song alignment');
  assert(Array.isArray(data.notes), 'Beat stage requires native notes');
  for (const [index, n] of data.notes.entries()) {
    assert(object(n) && ['estimated', 'excluded'].includes(n.status) && Number.isInteger(n.lane) && n.lane >= 0, `Invalid native note ${index}`);
    assert(Array.isArray(n.points) && n.points.every((p, i) => Array.isArray(p) && p.length === 2 && p.every(finite) && (!i || p[0] > n.points[i - 1][0])), `Invalid native positions for note ${index}`);
    if (n.status === 'estimated') assert(finite(n.target_seconds) && finite(n.prediction_uncertainty_seconds) && n.prediction_uncertainty_seconds >= 0, `Invalid source clock for note ${index}`);
  }
  for (const r of data.head_registration?.notes ?? []) assert(Number.isInteger(r.note) && r.note >= 0 && r.note < data.notes.length, 'Native registration references an unknown note');
  for (const r of data.scroll_motion?.coordinate_registration?.chunks ?? []) for (const h of r.head_offsets ?? []) {
    assert(Number.isInteger(h.note) && h.note >= 0 && h.note < data.notes.length && finite(h.offset_pixels), 'Invalid registered head offset');
  }
  if (data.layout?.lanes?.length >= 2) {
    assert(finite(data.analysis_width) && data.analysis_width > 0 && finite(data.analysis_height) && data.analysis_height > 0, 'Native geometry requires positive dimensions');
    assert(data.layout.lanes.every((l, i) => finite(l.x) && (!i || l.x > data.layout.lanes[i - 1].x)), 'Lane positions must be finite and increasing');
  }
}
