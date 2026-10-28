import {contracts, NATURAL_SPLITS, RECOVERABLE} from '../contracts.ts';
import {entries, sum} from '../math.ts';
import {fit} from './coordinates.ts';
import {targetRange} from './line_bounds.ts';
import {spacingFailures} from './spacing.ts';
import {conflicts} from './chords.ts';
import type {CoordinateSupport, Note, RecordData} from '../types.ts';
const F = contracts.recovery, C = contracts.coordinates;

export function directClockRows(notes: Note[], groups: RecordData[], phase: number, range: number[]): number[] {
  const result = [];
  notes.forEach((n, i) => {
    const beat = n.beat_reconstruction ?? {};
    if (n.status !== 'estimated' || beat.status !== 'restored' || !Object.hasOwn(beat, 'group_index')) return;
    const g = groups[beat.group_index], index = g.notes.indexOf(i), domains = g.unconstrained_row_domains;
    if (domains?.length && domains[index][0] !== domains[index][1]) return;
    const interval = n.video_target_range, target = n.target_seconds;
    if (!interval || target + range[0] - phase < interval[0] - 1e-8 || target + range[1] - phase > interval[1] + 1e-8) return;
    result.push(i);
  });
  return result;
}

export function candidateWindow(note: Note, notes: Note[], groups: RecordData[]): [number, number[], number[]] | null {
  const radius = C.reference_radius_seconds;
  if (RECOVERABLE.includes(note.reason)) {
    const seed = note.timing_reconstruction?.unaccepted_previous_estimate?.target_seconds;
    return seed != null && Number.isFinite(seed) ? [seed, [seed - radius, seed + radius], []] : null;
  }
  const beat = note.beat_reconstruction ?? {};
  if (note.reason === 'beat_timing_reconstruction_failed' && beat.reason === 'no_natural_beat_subdivision' && Object.hasOwn(beat, 'group_index')) {
    const g = groups[beat.group_index], unsupported = g.status === 'partial' ? (g.unsupported_indices ?? []) : [];
    const omitted = unsupported.length ? unsupported.map(j => g.notes[j]) : g.notes;
    const seed = sum(note.video_target_range) / 2;
    return [seed, [seed - radius, seed + radius], omitted];
  }
  const domain = note.reason === 'beat_timing_reconstruction_failed' && ['native_coordinate_domains_incompatible', 'ambiguous_beat_rows'].includes(beat.reason);
  const geometry = ['beat_grid_conflicts_with_spatial_spacing', 'beat_grid_conflicts_with_native_chord'].includes(note.reason);
  if (!(domain || geometry) || !Object.hasOwn(beat, 'group_index')) return null;
  const omitted = groups[beat.group_index].notes, intervals = omitted.map(i => notes[i].video_target_range);
  return [sum(note.video_target_range) / 2, [Math.min(...intervals.map(v => v[0])) - radius, Math.max(...intervals.map(v => v[1])) + radius], omitted];
}

export function chooseRow(models: RecordData[], sections: number[][], origin: number, phase: number, clockRange: number[] | null = null): RecordData {
  let lower = Math.max(...models.map(m => m.range[0])), upper = Math.min(...models.map(m => m.range[1]));
  if (lower > upper) return {status: 'failed', reason: 'incompatible_native_coordinate_models'};
  if (clockRange) {
    lower = Math.max(lower, clockRange[0]); upper = Math.min(upper, clockRange[1]);
    if (lower > upper) return {status: 'failed', reason: 'incompatible_native_and_clock_ranges'};
  }
  for (let si = 0; si < sections.length; si++) {
    const [lo, hi, bpm] = sections[si], base = origin + lo + phase;
    if (!(origin + lo <= lower && upper < origin + hi)) continue;
    const targets = models.flatMap(m => m.model.references.map(r => r.target_seconds));
    for (const split of NATURAL_SPLITS) {
      const step = 60 / (bpm * split);
      if (targets.some(t => Math.abs((t - base) / step - Math.round((t - base) / step)) > 1e-6)) continue;
      const a = Math.ceil((lower - base) / step - 1e-8), b = Math.floor((upper - base) / step + 1e-8);
      if (a > b) continue;
      if (a < b) return {status: 'failed', reason: 'ambiguous_native_coordinate_rows', native_target_range: [lower, upper]};
      return {status: 'restored', section: si, split, row: a, target_seconds: base + a * step, native_target_range: [lower, upper]};
    }
    return {status: 'failed', reason: 'native_coordinates_outside_natural_rows', native_target_range: [lower, upper]};
  }
  return {status: 'failed', reason: 'native_coordinate_interval_crosses_tempo_boundary', native_target_range: [lower, upper]};
}

export function interpolationModels(index: number, notes: Note[], support: CoordinateSupport, eligible: number[], section: number[], origin: number, window: number[] | null = null): RecordData[] {
  const models = [];
  for (const [number, heads] of entries(support.chunks)) {
    if (!heads[index]) continue;
    const refs = entries(heads).filter(([j]) => eligible.includes(j) && origin + section[0] <= notes[j].target_seconds && notes[j].target_seconds < origin + section[1] &&
      (!window || window[0] <= notes[j].target_seconds && notes[j].target_seconds <= window[1])).map(([j, h]) => ({note: j, target_seconds: notes[j].target_seconds, ...h}));
    const model = fit(refs, support.lane_spacing_pixels);
    if (!model) continue;
    const range = targetRange(model, heads[index].offset, C.maximum_native_error_spacing * model.lane_spacing_pixels);
    const [lo, hi] = model.reference_target_range;
    if (!(lo <= range[0] && range[1] <= hi)) continue;
    models.push({chunk: number, head: heads[index], model, range});
  }
  return models;
}

export function blockValidation(index: number, result: RecordData, notes: Note[], support: CoordinateSupport, spacing: number, motion: RecordData, chords: RecordData[]): RecordData[] {
  const candidate = notes.map(n => ({...n}));
  Object.assign(candidate[index], {status: 'estimated', target_seconds: result.target_seconds, fit_method: 'native_beat_coordinate_interpolation'});
  const proofs = result.models.map(m => ({note: index, chunk: m.chunk, references: m.model.references}));
  const failures = spacingFailures(candidate, spacing, motion, {...support, recovery_reference_sets: proofs}, null, null, [index]);
  failures.push(...conflicts(candidate, chords.filter(p => p.peer_notes.includes(index))));
  const references = new Set(result.models.flatMap(m => m.model.references.map(r => r.note)));
  return failures.filter(f => f.note === index || references.has(f.note));
}

export function recover(notes: Note[], support: CoordinateSupport | null, sections: number[][], origin: number, phase: number | null, alignmentError: number,
  groups: RecordData[] = [], phaseRange: number[] | null = null, spacing: number | null = null, motion: RecordData | null = null, chords: RecordData[] = []): RecordData {
  if (!support || phase == null) return {};
  const frozen = notes.flatMap((n, i) => n.status === 'estimated' && n.beat_reconstruction?.status === 'restored' ? [i] : []);
  const direct = groups.length ? directClockRows(notes, groups, phase, phaseRange ?? [phase, phase]) : [], results = {};
  notes.forEach((n, i) => {
    const candidate = candidateWindow(n, notes, groups);
    if (!candidate) return;
    const [seed, window, omitted] = candidate, eligible = omitted.length ? direct.filter(i => !omitted.includes(i)) : frozen;
    const section = sections.find(([lo, hi]) => origin + lo <= seed && seed < origin + hi);
    if (!section) return;
    let models = interpolationModels(i, notes, support, eligible, section, origin, window), fallback = false;
    if (!models.length && groups.length && spacing !== null && motion !== null) {
      models = interpolationModels(i, notes, support, direct.filter(i => !omitted.includes(i)), section, origin); fallback = !!models.length;
    }
    if (!models.length) return;
    const clockRange = n.beat_reconstruction?.reason === 'ambiguous_beat_rows' ? n.video_target_range : null;
    const result = chooseRow(models, sections, origin, phase, clockRange);
    Object.assign(result, {format: F, source_failure: n.reason, reference_window_center_seconds: seed, models});
    if (clockRange) result.clock_constraint_range = clockRange;
    if (omitted.length) Object.assign(result, {excluded_reference_group: [...omitted].sort((a, b) => a - b), reference_selection: 'unique_source_clock_rows'});
    if (fallback) {
      Object.assign(result, {reference_scope: 'complete_native_block', reference_selection: 'unique_source_clock_rows'});
      if (result.status === 'restored') {
        const failures = blockValidation(i, result, notes, support, spacing, motion, chords);
        if (failures.length) Object.assign(result, {status: 'failed', reason: 'native_block_recovery_failed_pair_validation', validation_failures: failures});
      }
    }
    results[i] = result;
  });
  for (const [i, r] of entries<RecordData>(results)) {
    if (r.status !== 'restored') {
      const n = notes[i];
      if (RECOVERABLE.includes(n.reason) && r.native_target_range &&
        ['ambiguous_native_coordinate_rows', 'native_coordinates_outside_natural_rows', 'native_coordinate_interval_crosses_tempo_boundary'].includes(r.reason)) {
        const [lo,hi] = r.native_target_range;
        Object.assign(n, {reason:'beat_timing_reconstruction_failed', video_target_range:[lo-alignmentError,hi+alignmentError],
          prediction_uncertainty_seconds:(hi-lo)/2+alignmentError,
          timing_reconstruction:{status:'restored',method:'native_coordinate_interval',previous_motion_attempt:n.timing_reconstruction},
          beat_reconstruction:{...n.beat_reconstruction,status:'failed',method:F.method,reason:r.reason}});
        r.native_interval_status='restored';
      }
      continue;
    }
    const n = notes[i], target = r.target_seconds, [lo, hi] = r.native_target_range;
    const rejected = RECOVERABLE.includes(n.reason) ? {} : {rejected_beat_assignment: n.beat_reconstruction, rejected_clock_target_range: n.video_target_range};
    Object.assign(n, {status: 'estimated', reason: null, target_seconds: target, fit_method: 'native_beat_coordinate_interpolation',
      prediction_uncertainty_seconds: Math.max(target - lo, hi - target) + alignmentError, video_target_range: [lo - alignmentError, hi + alignmentError],
      beat_reconstruction: {status: 'restored', method: F.method, section: r.section, split: r.split, row: r.row},
      timing_reconstruction: {status: 'restored', method: F.method, previous_motion_attempt: n.timing_reconstruction, ...rejected}});
  }
  return results;
}

export function validateReferences(notes: Note[], results: RecordData): RecordData[] {
  const warnings=[];
  for (const [index,proof] of entries<RecordData>(results)) {
    const n=notes[index];
    if (n.status!=='estimated' && proof.native_interval_status!=='restored') continue;
    const references=proof.models.flatMap(m=>m.model.references);
    if (!references.some(r=>notes[r.note].status!=='estimated'||Math.abs(notes[r.note].target_seconds-r.target_seconds)>1e-8)) continue;
    const reason='native_coordinate_reference_failed_validation';
    const original=n.timing_reconstruction?.previous_motion_attempt, range=n.timing_reconstruction?.rejected_clock_target_range;
    const retained=original?.status==='restored'&&Array.isArray(range)&&range.length===2&&range.every(Number.isFinite)&&range[0]<range[1];
    Object.assign(n,{status:'excluded',reason:retained?'beat_timing_reconstruction_failed':reason,target_seconds:null,
      beat_reconstruction:{...n.beat_reconstruction,status:'failed',reason}});
    if (retained) {
      n.timing_reconstruction={...original,rejected_coordinate_reconstruction:{status:'failed',reason,method:n.timing_reconstruction.method}};
      n.video_target_range=[...range];n.prediction_uncertainty_seconds=(range[1]-range[0])/2;
      proof.native_interval_status='original_clock_retained';
    } else {
      n.timing_reconstruction={...n.timing_reconstruction,status:'failed',reason};
      if (proof.native_interval_status==='restored') proof.native_interval_status='failed';
    }
    Object.assign(proof,{status:'failed',reason});
    warnings.push({note:index,lane:n.lane,reason,check:'timing_reconstruction',visible_start_seconds:n.points[0][0],
      visible_end_seconds:n.points.at(-1)[0],observed_points:n.points.length});
  }
  return warnings;
}
