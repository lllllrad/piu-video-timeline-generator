import {spacingFailures} from './spacing.ts';
import {prepare, conflicts} from './chords.ts';
import type {CoordinateSupport, Note, RecordData} from '../types.ts';

export function validate(data: RecordData, notes: Note[], spacing: number | null, support: CoordinateSupport | null,
  baseline: number[] | null = null, changed: number[] | null = null): RecordData[][] {
  if (spacing === null) return [[], [], []];
  const checks = [], warnings = spacingFailures(notes, spacing, data.scroll_motion ?? null, support, checks, baseline, changed);
  const exclude = w => {
    const n = notes[w.note];
    Object.assign(n, {status: 'excluded', reason: w.reason, target_seconds: null, beat_reconstruction: {...n.beat_reconstruction, status: 'failed', reason: w.reason}});
  };
  warnings.forEach(w => { w.reason = 'beat_grid_conflicts_with_spatial_spacing'; exclude(w); });
  const chords = prepare({...data, notes}, spacing), constraints = chords.filter(p => !changed || p.peer_notes.some(i => changed.includes(i)));
  const bad = conflicts(notes, constraints);
  bad.forEach(exclude);
  return [[...warnings, ...bad], chords, checks];
}

export function spacingSupportedNotes(notes: Note[], groups: RecordData[], fits: RecordData[], spacing: number,
  motion: RecordData | null, support: CoordinateSupport | null = null, chords: RecordData[] = []): number[] {
  const candidate = notes.map(n => ({...n}));
  groups.forEach((g, i) => g.notes.forEach((index, j) => {
    const f = fits[i];
    if (['restored', 'partial'].includes(f.status) && f.targets[j] != null) candidate[index].target_seconds = f.targets[j];
    else candidate[index].status = 'excluded';
  }));
  const rejected = new Set([...spacingFailures(candidate, spacing, motion, support), ...conflicts(candidate, chords)].map(w => w.note));
  return candidate.flatMap((n, i) => n.status === 'estimated' && !rejected.has(i) ? [i] : []);
}
