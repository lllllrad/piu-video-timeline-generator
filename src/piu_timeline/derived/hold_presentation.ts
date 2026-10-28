/** Interpret saved hold geometry and independent channels for report/chart consumers. */
import {annotateMatches, bracket, disputedRefresh, onsetOverlaps, processingSupport, receptorEvidence} from './evidence.ts';
import {chartProjection, projectTypes} from './hold_projection.ts';
import {recoverRows} from './recovery.ts';
import {attachRecoveredLabels, recoverPreHold} from './labels.ts';
import type {RecordData} from './types.ts';

export function present(input: RecordData, preHoldProofs: Record<string, RecordData> = {}): RecordData {
  let data = annotateMatches(input);
  const view = chartProjection(data);
  if (!data.hold_analysis || !Object.keys(data.hold_analysis).length) return view;
  const notes = view.notes, holds = data.hold_analysis.holds ?? [], projected = view.hold_analysis.holds, tails = view.hold_analysis.observed_tail_roles;
  const suppressed = new Set<number>([...projected, ...view.hold_analysis.unresolved_holds].flatMap(h => h.covered_notes).concat(tails.map(r => r.tail_note)));
  const duringHold = (lo, hi) => holds.some(h => hi >= (h.start_censored ? h.start_range[1] : (h.start_range[0] + h.start_range[1]) / 2) + .04 && lo <= (h.end_range ? (h.end_range[0] + h.end_range[1]) / 2 : h.last_body_seconds));
  const inputMatches = [...data.matches], assigned = new Set(inputMatches.map(m => m.note)), deferred = [];
  for (const m of data.deferred_matches ?? []) {
    const i = m.note;
    if (assigned.has(i) || notes[i].status !== 'estimated' || notes[i].note_type === 'hold' || data.combo_events[m.combo_event].delta !== 1) continue;
    const lo = m.combo_lower_seconds, hi = m.combo_upper_seconds;
    const conflict = inputMatches.some(other => {
      const [a, b] = bracket(other);
      return a != null && b != null && Math.abs(b - hi) <= .025 && a <= hi && b >= lo && Math.abs(other.target_seconds - m.target_seconds) >= .025;
    });
    if (!conflict) deferred.push({...m, evidence_source: 'combo+lane_evidence', observation_lower_seconds: lo, observation_upper_seconds: hi, recovery_method: 'strict_row_alignment_with_independent_lane_evidence'});
  }
  inputMatches.push(...deferred);
  const guard = 2 * (data.median_frame_interval_seconds || .017), runs = receptorEvidence(data), owners = new Map<number, Set<number>>(), noteRuns = new Map<number, number[]>();
  for (const m of inputMatches) {
    if (suppressed.has(m.note)) continue;
    const [lo, hi] = bracket(m); if (lo == null || hi == null) continue;
    runs.forEach((r, ri) => { if (r.lane === notes[m.note].lane && onsetOverlaps(r, lo, hi, guard)) {
      if (!owners.has(ri)) owners.set(ri, new Set()); owners.get(ri).add(m.note);
      if (!noteRuns.has(m.note)) noteRuns.set(m.note, []); noteRuns.get(m.note).push(ri);
    } });
  }
  const independent = i => (noteRuns.get(i) ?? []).some(ri => owners.get(ri).size === 1 && owners.get(ri).has(i));
  let matches: RecordData[] = [];
  const ambiguous = [], processingConfirmed = new Set(), recovered = [];
  for (const original of inputMatches) {
    let m = original;
    if (suppressed.has(m.note) || notes[m.note].status !== 'estimated') continue;
    const [lo, hi] = bracket(m);
    if (lo != null && hi != null && processingSupport(data, m.note, lo, hi, guard)) processingConfirmed.add(m.note);
    const needsLane = m.recovery_method === 'strict_row_alignment_with_independent_lane_evidence';
    if ((needsLane || lo != null && hi != null && duringHold(lo, hi)) && !(independent(m.note) || processingSupport(data, m.note, lo, hi, guard))) ambiguous.push(m.note);
    else {
      if (needsLane) m = {...m, evidence_source: 'combo+' + (independent(m.note) ? 'lane_onset' : 'note_disappearance')};
      matches.push(m); if (needsLane) recovered.push(m.note);
    }
  }
  const laneReason = (index, key, suffix) => {
    const source = key === 'combo_events' ? 'combo_event' : 'judgment_event', processing = matches.some(m => m[source] === index && processingConfirmed.has(m.note));
    return 'tap_with_' + (processing ? 'note_disappearance' : 'independent_lane_onset') + '_during_' + suffix;
  };
  const events = key => {
    const sourceKey = key === 'combo_events' ? 'combo_event' : 'judgment_event', owned = new Set(matches.map(m => m[sourceKey]));
    const preHold = new Set(matches.filter(m => m.recovery_method === 'strict_judgment_before_accounted_hold').map(m => m.judgment_event));
    return (data[key] ?? []).map((original, i) => {
      const e = {...original};
      if (key === 'judgment_events' && preHold.has(i)) Object.assign(e, {status: 'matched', reason: 'tap_before_accounted_hold_regions'});
      if (key === 'combo_events' && matches.some(m => m.combo_event === i && m.aggregate_evidence_method)) Object.assign(e, {status: 'matched', reason: 'aggregate_counter_with_exclusive_lane_onsets'});
      if (key === 'combo_events' && owned.has(i) && e.reason === 'possible_hold_or_dense_stack') Object.assign(e, {status: 'matched', reason: laneReason(i, key, 'dense_interval')});
      const source = key === 'combo_events' ? 'combo' : 'judgment';
      if (!owned.has(i) && (data.conflicted_matches ?? []).some(m => disputedRefresh(data, m.note, [{...e, source, event: i}]))) Object.assign(e, {status: 'unresolved', reason: 'processing_conflicted_association'});
      if (e.label !== 'MISS' && (e.delta ?? 1) > 0 && duringHold(e.lower_seconds, e.upper_seconds)) {
        Object.assign(e, owned.has(i) ? {status: 'matched', reason: laneReason(i, key, 'hold')} : {status: 'hold_state_or_tap', reason: 'ongoing_hold_tick_not_new_press'});
      }
      return e;
    });
  };
  const [rowMatches, laneRecovered] = recoverRows({...data, notes, matches, combo_events: events('combo_events'), judgment_events: events('judgment_events'), hold_analysis: {...data.hold_analysis, holds: projected, observed_tail_roles: tails}});
  matches = rowMatches;
  const [earlyMatches, preHoldRecovered] = recoverPreHold(data, notes, matches, [...suppressed], preHoldProofs); matches = earlyMatches;
  let labeled = attachRecoveredLabels({...data, matches, combo_events: events('combo_events'), judgment_events: events('judgment_events')}); matches = labeled.matches;
  for (const m of matches) {
    const proof = data.counter_judgment_labels?.[String(m.combo_event)];
    if (proof && !m.judgment_label) Object.assign(m, {judgment_label: proof.label, judgment_event: null, judgment_label_source: 'post_combo_frames',
      judgment_observations: proof.observations.map(o => ({...o})), evidence_source: (m.evidence_source ?? 'combo') + '+judgment'});
  }
  let validated = annotateMatches({...data, notes, matches}); matches = validated.matches; data = {...data, conflicted_matches: validated.conflicted_matches};
  // Every generation repeats the same independent evidence and ownership checks.
  // Confirmed notes grow monotonically, so closure takes at most notes.length passes.
  for (let generation=2;;generation++) {
    const assigned=new Set(matches.map(m=>m.note));
    const [proposals]=recoverRows({...data,notes,matches,combo_events:events('combo_events'),judgment_events:labeled.judgment_events,
      hold_analysis:{...data.hold_analysis,holds:projected,observed_tail_roles:tails}});
    const fresh=proposals.filter(m=>!assigned.has(m.note)).map(m=>({...m,recovery_generation:generation}));
    if(!fresh.length)break;
    const checked=annotateMatches({...data,notes,matches:[...matches,...fresh]});
    const accepted=checked.matches.filter(m=>!assigned.has(m.note));
    matches=checked.matches;data={...data,conflicted_matches:checked.conflicted_matches};
    if(!accepted.length)break;
    laneRecovered.push(...accepted.map(m=>m.note));
    labeled=attachRecoveredLabels({...data,matches,combo_events:events('combo_events'),judgment_events:labeled.judgment_events});
    matches=labeled.matches;
  }
  validated=annotateMatches({...data,notes,matches});matches=validated.matches;data={...data,conflicted_matches:validated.conflicted_matches};
  const coverage = {...data.coverage, visible_note_heads: notes.filter(n => n.status === 'estimated').length, timed_note_heads: matches.length,
    matched_combo_updates: new Set(matches.filter(m => m.combo_event != null).map(m => m.combo_event)).size, judgment_only_note_heads: matches.filter(m => m.evidence_source === 'judgment').length,
    judgment_labeled_note_heads: matches.filter(m => m.judgment_label).length, unlabeled_timed_note_heads: matches.filter(m => !m.judgment_label).length,
    combo_frame_labeled_note_heads: matches.filter(m => m.judgment_label_source === 'post_combo_frames').length, long_notes: projected.length, sustained_recognition_spans: projected.reduce((n, h) => n + h.input.segments.length, 0)};
  const limitations = (data.limitations ?? []).map(s => s.replaceAll('Holds, rolls', 'Rolls'));
  limitations.push('Long-note recognition is a sustained visual state; neither a separate press per tick nor physical release is measured.');
  const excluded = {}; for (const n of notes) if (n.status === 'excluded') { const reason = String(n.reason ?? null); excluded[reason] = (excluded[reason] ?? 0) + 1; }
  return {...data, notes, matches, limitations, excluded_notes: excluded, miss_candidates: (data.miss_candidates ?? []).filter(c => !suppressed.has(c.note)),
    combo_events: events('combo_events'), judgment_events: labeled.judgment_events, hold_tick_ambiguous_notes: ambiguous.filter(i => !laneRecovered.includes(i) && !preHoldRecovered.includes(i)),
    recovered_pre_hold_notes: preHoldRecovered, recovered_dense_notes: recovered,
    recovered_bounded_target_notes:matches.filter(m=>m.recovery_method==='exclusive_bounded_target_with_synchronized_refreshes').map(m=>m.note),
    recovered_lane_supported_notes:laneRecovered.filter(i=>!matches.some(m=>m.note===i&&m.recovery_method==='exclusive_bounded_target_with_synchronized_refreshes')), hold_analysis: view.hold_analysis, coverage,
    note_type_diagnostics: projectTypes(data, notes, projected)};
}
