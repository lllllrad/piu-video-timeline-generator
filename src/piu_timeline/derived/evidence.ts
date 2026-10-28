/** Shared access and ownership rules for saved visual evidence. */
import type {RecordData} from './types.ts';
export const ASSOCIATION_FORMAT = {schema: 1, revision: 1, policy: 'processing_conflicts_quarantined'};
export const receptorEvidence = (data: RecordData): RecordData[] => data.visual_channels?.receptors?.events ?? data.hold_analysis?.receptor_runs ?? [];
export const processingEvidence = (data: RecordData): RecordData[] => data.visual_channels?.processing?.notes ?? [];
export const bracket = m => [Object.hasOwn(m, 'observation_lower_seconds') ? m.observation_lower_seconds : m.combo_lower_seconds,
  Object.hasOwn(m, 'observation_upper_seconds') ? m.observation_upper_seconds : m.combo_upper_seconds];

export function assignments(data: RecordData): RecordData[] {
  const current = [...(data.matches ?? [])], notes = new Set(current.map(m => m.note));
  return [...current, ...(data.conflicted_matches ?? []).filter(m => !notes.has(m.note))];
}
export function partition(data: RecordData): RecordData {
  const original = assignments(data), confirmed = original.filter(m => !m.processing_conflict), conflicted = original.filter(m => m.processing_conflict);
  const result: RecordData = {...data, matches: confirmed, conflicted_matches: conflicted, association_view_format: ASSOCIATION_FORMAT};
  if (data.coverage) {
    const counts = {timed_note_heads: confirmed.length, matched_combo_updates: new Set(confirmed.filter(m => m.combo_event != null).map(m => m.combo_event)).size,
      judgment_only_note_heads: confirmed.filter(m => m.evidence_source === 'judgment').length, judgment_labeled_note_heads: confirmed.filter(m => m.judgment_label).length,
      unlabeled_timed_note_heads: confirmed.filter(m => !m.judgment_label).length, combo_frame_labeled_note_heads: confirmed.filter(m => m.judgment_label_source === 'post_combo_frames').length};
    result.coverage = {...data.coverage, ...Object.fromEntries(Object.entries(counts).filter(([k]) => Object.hasOwn(data.coverage, k)))};
  }
  return result;
}
export function disputedRefresh(data: RecordData, note: number, events: RecordData[]): boolean {
  for (const m of data.conflicted_matches ?? []) {
    if (m.note !== note) continue;
    const [lower, upper] = bracket(m);
    for (const e of events) {
      const key = {combo: 'combo_event', judgment: 'judgment_event'}[e.source];
      if (key && m[key] != null && m[key] === e.event && lower != null && upper != null && lower <= e.upper_seconds + 1e-6 && upper >= e.lower_seconds - 1e-6) return true;
      if (lower != null && upper != null && Math.abs(lower - e.lower_seconds) < 1e-6 && Math.abs(upper - e.upper_seconds) < 1e-6) return true;
    }
  }
  return false;
}
export function onsetOverlaps(run: RecordData, lo: number, hi: number, guard = 0): boolean {
  if (run.lit !== true || run.frames + (run.corroborating_lit_frames_after_flash ?? 0) < 2) return false;
  const interval = Object.hasOwn(run, 'onset_range') ? run.onset_range :
    (Object.hasOwn(run, 'previous_lit') ? run.previous_lit : false) === false && run.previous_seconds != null ? [run.previous_seconds, run.start_seconds] : null;
  return interval != null && interval[0] <= hi + guard && interval[1] >= lo - guard;
}
export function processingSupport(data: RecordData, note: number, lo: number, hi: number, guard = 0): RecordData | null {
  return processingEvidence(data).find(e => e.note === note && e.status === 'disappeared_near_receptor' && e.range[0] <= hi + guard && e.range[1] >= lo - guard) ?? null;
}
export function processingConflicts(data: RecordData, note: number, lo: number, hi: number, guard = 0): boolean {
  guard = Math.max(.075, guard);
  return processingEvidence(data).some(e => e.note === note && e.status === 'disappeared_near_receptor' && (e.range[1] < lo - guard || e.range[0] > hi + guard));
}
export function afterRefresh(event: RecordData, upper: number, guard = 0): RecordData | null {
  const p = event.passage_evidence;
  if (event.status !== 'passed_target' || !p) return null;
  const [lo, hi] = p.range;
  return 0 < hi - lo && hi - lo <= .05 && lo > upper + Math.max(.075, guard) + 1e-9 ? p : null;
}
export function annotateMatches(data: RecordData): RecordData {
  if (!data.visual_channels || !Object.keys(data.visual_channels).length) return partition(data);
  const guard = 2 * (data.median_frame_interval_seconds || .017), matches = [];
  for (const original of assignments(data)) {
    const match = {...original}, ni = match.note, observed = processingEvidence(data).find(e => e.note === ni);
    if (observed) { delete match.processing_conflict; delete match.processing_passage_after_refresh; }
    const refs = [`motion:${ni}`];
    for (const [key, prefix] of [['combo_event', 'combo:'], ['judgment_event', 'judgment:']]) if (match[key] != null) refs.push(prefix + match[key]);
    const [lo, hi] = bracket(match);
    if (lo != null && hi != null) {
      receptorEvidence(data).forEach((run, i) => { if (run.lane === data.notes[ni].lane && onsetOverlaps(run, lo, hi, guard)) refs.push(run.id ?? `receptor:${i}`); });
      if (processingSupport(data, ni, lo, hi, guard)) refs.push(`processing:${ni}`);
    }
    match.visual_evidence = refs; match.processing_status = observed?.status ?? 'unavailable';
    if (observed?.status === 'disappeared_near_receptor' && lo != null && hi != null) match.processing_conflict = processingConflicts(data, ni, lo, hi, guard);
    if (observed && hi != null) { const p = afterRefresh(observed, hi, guard); if (p) Object.assign(match, {processing_conflict: true, processing_passage_after_refresh: p}); }
    matches.push(match);
  }
  return partition({...data, matches, conflicted_matches: []});
}
export function notePolicy(data: RecordData, note: RecordData): RecordData | null {
  const target = note.target_seconds;
  if (target == null) return null;
  const regions = (data.chart_policy?.regions ?? []).filter(r => r.playback_start_seconds <= target && target < r.playback_end_seconds);
  if (!regions.length) return null;
  const processing = regions.find(r => r.processing !== 'standard')?.processing ?? 'standard';
  return {regions: regions.map(r => r.id), processing, suppress_timing: processing === 'exclude_timing' || processing === 'hold_state_only' && note.note_type !== 'hold',
    check_exceptions: [...new Set(regions.flatMap(r => r.check_exceptions))].sort(), reasons: regions.map(r => r.reason)};
}

export function associationPatch(data: RecordData, annotate = false): RecordData {
  const result = annotate ? annotateMatches(data) : partition(data);
  return Object.fromEntries(['matches', 'conflicted_matches', 'association_view_format', 'coverage'].filter(k => Object.hasOwn(result, k)).map(k => [k, result[k]]));
}

export function policyProjection(data: RecordData): RecordData {
  if (!data.chart_policy?.regions?.length) return {};
  const excluded = new Set(data.notes.flatMap((n, i) => n.status === 'estimated' && notePolicy(data, n)?.suppress_timing ? [i] : []));
  if (!excluded.size) return {};
  const matches = data.matches.filter(m => !excluded.has(m.note));
  const holds = (data.hold_analysis?.holds ?? []).map(h => excluded.has(h.display_note) ? {...h, input: {...h.input, segments: [], recognition_envelope: null, policy_retained_observations: h.input.segments}} : h);
  return {matches, hold_analysis: {...data.hold_analysis, holds}, coverage: {...data.coverage, timed_note_heads: matches.length, policy_excluded_note_heads: excluded.size}};
}
