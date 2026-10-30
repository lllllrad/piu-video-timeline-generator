/** Pure beat reconstruction. Reference acquisition and promotion belong to the caller. */
import {contracts, RECOVERABLE} from '../contracts.ts';
import {entries} from '../math.ts';
import {parse, grid, constantTempo} from '../charts/ucs.ts';
import {prepare as coordinateSupport} from './coordinates.ts';
import {prepare as chordSupport} from './chords.ts';
import {fitPhase} from './phase.ts';
import {recover,validateRecovery} from './recovery.ts';
import {validate, spacingSupportedNotes} from './validation.ts';
import type {Note, RecordData} from '../types.ts';
import {validateBeatInput} from '../validate.ts';

export interface BeatInput {
  schema: 1;
  data: RecordData;
  reference: RecordData;
  timing_text: string | null;
  preparation?: RecordData | null;
}

export function reconstruct(input: BeatInput): RecordData {
  validateBeatInput(input);
  const {reference:ref,preparation,data}=input,native={};
  const result: RecordData = {contract: {format: contracts.timing, reference: ref}, status: ref.status, warnings: [], groups: []};
  if (preparation) result.reference_preparation = preparation;
  if (ref.status !== 'available') {
    result.warnings = [{lane: 0, reason: 'beat_reference_unavailable', check: 'timing_reconstruction',
      failure_detail: preparation?.status === 'failed' ? preparation.reason : ref.reason, observed_points: 0,
      visible_start_seconds: data.start_seconds ?? 0, visible_end_seconds: data.end_seconds ?? data.start_seconds ?? 0}];
    return {...native,beat_timing: result};
  }
  if (typeof input.timing_text !== 'string') throw new Error('Available beat reference requires timing text');
  const doc = parse(input.timing_text), officialGrid = grid(doc), settings: Record<string, string> = {}, sections: number[][] = [];
  doc.sections.forEach((s, si) => {
    Object.assign(settings, Object.fromEntries(s.directives));
    const start = officialGrid.find(r => r[0] === si)[2].number(), bpm = Number(settings.BPM);
    sections.push([start, start + s.rows.length * 60 / (bpm * Number(settings.Split)), bpm]);
  });
  if (sections.slice(1).some((b, i) => b[0] < sections[i][1] - 1e-6)) throw new Error('Overlapping UCS timing sections prevent beat reconstruction');
  const origin = ref.song_start_seconds, estimated = data.notes.filter(n => n.status === 'estimated');
  const latest = estimated.length ? Math.max(...estimated.map(n => n.target_seconds + n.prediction_uncertainty_seconds - origin)) : sections.at(-1)[1];
  if (latest >= sections.at(-1)[1] && constantTempo(doc, ref.constant_tempo_bpm)) {
    const [lo, hi, bpm] = sections.at(-1), step = 60 / (bpm * Number(settings.Split)), end = lo + (Math.ceil((latest - lo) / step) + 1) * step;
    if (end - hi > 900) throw new Error('Timing extension exceeds supported song duration');
    sections[sections.length - 1] = [lo, end, bpm];
    result.timing_extension = {basis: 'constant_tempo_catalogue_and_template', original_end_seconds: hi, extended_end_seconds: end, review_required: true};
  }
  const notes: Note[] = data.notes.map(n => ({...n})), groups = new Map<string, {si: number; bar: number; indices: number[]}>();
  notes.forEach((n, i) => {
    if (n.status !== 'estimated') return;
    const time = n.target_seconds - origin, si = sections.findIndex(([lo, hi]) => lo <= time && time < hi);
    const bar = si < 0 ? 0 : Math.floor((time - sections[si][0]) / (contracts.timing.group_beats * 60 / sections[si][2])), key = `${si},${bar}`;
    if (!groups.has(key)) groups.set(key, {si, bar, indices: []});
    groups.get(key).indices.push(i);
  });
  if (!groups.size) {
    Object.assign(result, {status: 'failed', warnings: [{lane: 0, reason: 'no_supported_note_targets', check: 'timing_reconstruction', observed_points: 0,
      visible_start_seconds: data.start_seconds ?? 0, visible_end_seconds: data.end_seconds ?? data.start_seconds ?? 0}]});
    return {...native,beat_timing: result};
  }
  const lanes = data.layout?.lanes ?? [], spacing = lanes.length >= 2 ? (lanes[1].x - lanes[0].x) * data.analysis_width : null;
  const chords = spacing ? chordSupport(data, spacing) : [];
  result.native_chords = chords;
  const proposals = [...groups.values()].map(({si, bar, indices}) => {
    indices.sort((a, b) => notes[a].target_seconds - notes[b].target_seconds);
    const g: RecordData = {notes: indices, section: si, beat_group: bar, targets: indices.map(i => notes[i].target_seconds), errors: indices.map(i => notes[i].prediction_uncertainty_seconds)};
    g.native_chords = chords.filter(p => p.peer_notes.every(i => indices.includes(i))).map(p => ({...p, indices: p.peer_notes.map(i => indices.indexOf(i))}));
    if (si < 0) g.invalid = 'outside_official_timing_sections';
    else Object.assign(g, {bpm: sections[si][2], origin: origin + sections[si][0]});
    return g;
  });
  let support = spacing ? coordinateSupport(data, spacing) : null;
  if (support) for (const g of proposals) {
    g.native_coordinates = entries(support.chunks).filter(([, heads]) => entries(heads).some(([i]) => g.notes.includes(i))).map(([number, heads]) => ({
      chunk: number, lane_spacing_pixels: spacing,
      heads: Object.fromEntries(entries(heads).filter(([i]) => g.notes.includes(i)).map(([i, h]) => [g.notes.indexOf(i), {...h, native_note: i}])),
      neighbor_heads: Object.fromEntries(entries(heads).filter(([i]) => !g.notes.includes(i)))}));
  }
  const validator = spacing ? fits => spacingSupportedNotes(notes, proposals, fits, spacing, data.scroll_motion ?? null, support, chords) : undefined;
  const phase = fitPhase(proposals, ref.alignment_uncertainty_seconds, validator);
  Object.assign(result, {song_phase_range: phase.phase_range ?? null, song_phase_correction_seconds: phase.phase ?? null,
    phase_resolution_seconds: phase.resolution_seconds ?? null, phase_trials: phase.phase_trials ?? [], phase_consistent_notes: phase.consistent_notes ?? null});
  proposals.forEach((g, i) => {
    const fit = phase.fits[i];
    result.groups.push({notes: g.notes, section: g.section, beat_group: g.beat_group, ...fit});
    g.notes.forEach((index, j) => {
      const n = notes[index], before = n.target_seconds;
      n.video_target_range = [before - n.prediction_uncertainty_seconds, before + n.prediction_uncertainty_seconds];
      const accepted = ['restored', 'partial'].includes(fit.status) && fit.targets[j] != null;
      let failure = fit.reason;
      if (!accepted && fit.status === 'partial') {
        const [lo, hi] = fit.row_domains[j];
        failure = (fit.unsupported_indices ?? []).includes(j) ? 'no_natural_beat_subdivision' : (fit.incompatible_chord_indices ?? []).includes(j) ?
          'native_chord_domains_incompatible' : lo > hi ? 'native_coordinate_domains_incompatible' : 'ambiguous_beat_rows';
      }
      n.beat_reconstruction = {status: accepted ? 'restored' : 'failed', group_index: result.groups.length - 1,
        ...Object.fromEntries(['split', 'phase_range'].filter(k => Object.hasOwn(fit, k)).map(k => [k, fit[k]])), ...(!accepted ? {reason: failure} : {})};
      if (!accepted) {
        const pts = n.points ?? [];
        result.warnings.push({note: index, lane: n.lane, reason: 'beat_timing_reconstruction_failed', check: 'timing_reconstruction', failure_detail: failure,
          observed_points: pts.length, visible_start_seconds: pts.length ? pts[0][0] : n.target_seconds, visible_end_seconds: pts.length ? pts.at(-1)[0] : n.target_seconds});
        Object.assign(n, {status: 'excluded', reason: 'beat_timing_reconstruction_failed', target_seconds: null});
      } else {
        const target = fit.targets[j];
        Object.assign(n, {target_seconds: target, prediction_uncertainty_seconds: Math.max(n.prediction_uncertainty_seconds + Math.abs(target - before), ref.alignment_uncertainty_seconds)});
      }
    });
  });
  support = spacing ? coordinateSupport({...data, notes}, spacing, true) : null;
  const [initialWarnings, initialChords, initialChecks] = validate(data, notes, spacing, support);
  result.warnings.push(...initialWarnings);
  support = spacing ? coordinateSupport({...data, notes}, spacing, true) : null;
  const recovered = recover(notes, support, sections, origin, phase.phase ?? null, ref.alignment_uncertainty_seconds, result.groups, phase.phase_range ?? null, spacing, data.scroll_motion ?? null, chords);
  if (support) support.recovery_reference_sets = entries<RecordData>(recovered).filter(([i]) => notes[i].status === 'estimated')
    .flatMap(([i, p]) => p.models.map(m => ({note: i, chunk: m.chunk, references: m.model.references})));
  const [finalWarnings, finalChords, finalChecks] = validate(data, notes, spacing, support, support?.reference_notes ?? null,
    entries(recovered).filter(([i]) => notes[i].status === 'estimated').map(([i]) => i));
  result.warnings.push(...finalWarnings);
  result.coordinate_checks = [...initialChecks.map(c => ({...c, stage: 'reference_validation'})), ...finalChecks.map(c => ({...c, stage: 'recovery_validation'}))];
  result.native_chords = [...new Map([...initialChords, ...finalChords].map(p => [p.peer_notes.join(','), p])).values()];
  result.warnings.push(...validateRecovery(notes,recovered));
  result.native_coordinate_recovery = entries<RecordData>(recovered).map(([i, p]) => ({note: i, ...p}));
  const restored = entries<RecordData>(recovered).filter(([i]) => notes[i].status === 'estimated').map(([i]) => i);
  const intervals = entries<RecordData>(recovered).filter(([,p]) => p.native_interval_status === 'restored').map(([i]) => i);
  for (const index of intervals) {
    const n=notes[index],p=recovered[index];
    result.warnings.push({note:index,lane:n.lane,reason:'beat_timing_reconstruction_failed',check:'timing_reconstruction',
      failure_detail:p.reason,native_interval_status:'restored',native_target_range:n.video_target_range,
      visible_start_seconds:n.points[0][0],visible_end_seconds:n.points.at(-1)[0],observed_points:n.points.length});
  }
  const nativeRestored = [...restored,...intervals].filter(i=>RECOVERABLE.includes(recovered[i].source_failure)), reconstruction = {...data.timing_reconstruction};
  if (restored.length || nativeRestored.length) {
    result.warnings = result.warnings.filter(w=>!(restored.includes(w.note) && w.reason===recovered[w.note].source_failure));
    const remaining = (reconstruction.warnings ?? []).filter(w=>!(nativeRestored.includes(w.note) && w.reason===recovered[w.note].source_failure));
    Object.assign(reconstruction, {warnings: remaining, status: remaining.length ? 'failed' : 'restored', failed_notes: new Set(remaining.map(w => w.note)).size,
      restored_notes: (reconstruction.restored_notes ?? 0) + nativeRestored.length});
  }
  result.status = result.warnings.length ? 'failed' : 'restored';
  return {notes, beat_timing: result, timing_reconstruction: reconstruction};
}
