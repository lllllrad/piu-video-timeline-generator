import {contracts} from '../contracts.ts';
import {compare} from '../math.ts';
import {constrain as chordDomains} from './chords.ts';
import {constrain as coordinateDomains} from './domains.ts';
import type {Interval, RecordData} from '../types.ts';

export function fitGrid(targets: number[], errors: number[], bpm: number, origin: number,
  splits = contracts.timing.natural_splits, phaseError = 0, chords: RecordData[] = [], coordinates: RecordData[] = []): RecordData {
  if (targets.length !== errors.length) throw new Error('Target and uncertainty counts differ');
  if (!Number.isFinite(bpm) || bpm <= 0) throw new Error('Beat fitting requires positive BPM');
  let incompatible = null, partial = null;
  const support = r => [(r.targets ?? []).filter(t => t != null).length, -(r.unsupported_indices ?? []).length];
  for (const split of splits?.length ? splits : contracts.timing.natural_splits) {
    const step = 60 / (bpm * split);
    const original: Interval[] = targets.map((t, i) => [Math.ceil((t - errors[i] - phaseError - origin) / step - 1e-8), Math.floor((t + errors[i] + phaseError - origin) / step + 1e-8)]);
    const unsupported = original.flatMap(([lo, hi], i) => lo > hi ? [i] : []);
    if (unsupported.length && phaseError) continue;
    const [chordOptions, proofs] = chordDomains(original, step, chords);
    const chordIndices = chordOptions.flatMap(([lo, hi], i) => lo > hi && proofs.some(p => p.indices.includes(i)) ? [i] : []);
    if (chordIndices.length) incompatible = 'native_chord_domains_incompatible';
    const [options, coordinateProofs] = coordinateDomains(chordOptions, step, origin, coordinates);
    if (options.some(([lo, hi]) => lo > hi) && !unsupported.length && !chordIndices.length) incompatible = 'native_coordinate_domains_incompatible';
    if (options.every(([lo, hi]) => lo > hi)) continue;
    const rows = options.map(([lo, hi]) => lo === hi ? lo : null);
    const known = targets.flatMap((t, i) => rows[i] != null ? [[t, rows[i]]] : []);
    if (known.slice(1).some(([b, rb], i) => b - known[i][0] > .025 && rb <= known[i][1])) continue;
    const constraints = {...(proofs.length ? {native_chord_constraints: proofs} : {}),
      ...(coordinateProofs.length ? {native_coordinate_constraints: coordinateProofs} : {}),
      ...(proofs.length || coordinateProofs.length ? {unconstrained_row_domains: original} : {})};
    if (rows.some(r => r == null)) {
      const reason = unsupported.length ? 'no_natural_beat_subdivision' : chordIndices.length ? 'native_chord_domains_incompatible' :
        options.some(([lo, hi]) => lo > hi) ? 'native_coordinate_domains_incompatible' : 'ambiguous_beat_rows';
      const result: RecordData = {status: 'failed', reason, split, row_domains: options, ...constraints,
        ...(chordIndices.length ? {incompatible_chord_indices: chordIndices} : {}), ...(unsupported.length ? {unsupported_indices: unsupported} : {})};
      if (known.length && phaseError === 0) Object.assign(result, {status: 'partial', rows, targets: rows.map(r => r == null ? null : origin + r * step),
        phase_range: [0, 0], unresolved_indices: rows.flatMap((r, i) => r == null ? [i] : [])});
      if (options.some(([lo, hi]) => lo > hi) && result.status === 'partial') {
        if (!partial || compare(support(result), support(partial)) > 0) partial = result;
        continue;
      }
      return partial && compare(support(partial), support(result)) > 0 ? partial : result;
    }
    const exact = rows.map(r => origin + r * step);
    const phaseLo = Math.max(-phaseError, ...targets.map((t, i) => t - errors[i] - exact[i]));
    const phaseHi = Math.min(phaseError, ...targets.map((t, i) => t + errors[i] - exact[i]));
    if (phaseLo > phaseHi + 1e-8) continue;
    return {status: 'restored', split, rows, targets: exact, phase_range: [phaseLo, phaseHi], ...constraints};
  }
  return partial ?? {status: 'failed', reason: incompatible ?? 'no_natural_beat_subdivision'};
}
