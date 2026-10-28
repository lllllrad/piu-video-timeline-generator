import {assignments, processingEvidence} from './evidence.ts';
import {entries} from './math.ts';
import type {RecordData} from './types.ts';
const counts = (records, field) => { const result = {}; for (const r of records) result[r[field]] = (result[r[field]] ?? 0) + 1; return result; };
const distinct = a => new Set(a ?? []).size;

export function exclusions(native: RecordData, projected: RecordData): RecordData {
  const warnings = [], exceptions = [], accounted = [], regions = projected.chart_policy?.regions ?? [];
  const represented = i => (projected.hold_analysis?.holds ?? []).some(h => {
    const p = h.component_evidence?.[i] ?? {};
    return (h.covered_notes ?? []).includes(i) && ['registered_cap', 'inside_connected_body'].includes(p.kind) && distinct(p.source_pts_seconds) >= 4;
  });
  (native.notes ?? []).forEach((n, i) => {
    const points = n.points ?? [];
    if (!points.length) return;
    const view = projected.notes[i];
    if (view.reason === 'long_note_body_or_tail' && represented(i)) { accounted.push({note: i, reason: 'represented_by_reconstructed_hold'}); return; }
    if (n.status !== 'excluded' && view.status !== 'excluded') return;
    const duplicate = n.duplicate_of;
    if (n.reason === 'duplicate_head_component' && Number.isInteger(duplicate) && 0 <= duplicate && duplicate < projected.notes.length) {
      const owner = projected.notes[duplicate], positions = new Map<number, number>(owner.points ?? []), errors = points.filter(([t]) => positions.has(t)).map(([t, y]) => Math.abs(y - positions.get(t)));
      const same = n.lane === owner.lane && errors.length >= 4 && errors.filter(e => e <= 2).length >= .8 * errors.length;
      if (same && (owner.status === 'estimated' || owner.reason === 'long_note_body_or_tail' && represented(duplicate))) {
        accounted.push({note: i, reason: 'represented_by_duplicate_owner', represented_by: duplicate}); return;
      }
    }
    const first = Math.min(...points.map(p => p[0])), last = Math.max(...points.map(p => p[0]));
    const reason = view.reason === 'long_note_body_or_tail' ? 'unverified_hold_component' : view.reason || n.reason || 'unspecified_exclusion';
    const record = {note: i, lane: n.lane, reason, visible_start_seconds: first, visible_end_seconds: last, observed_points: points.length, target_seconds: n.target_seconds ?? null};
    const allowed = regions.filter(r => (['exclude_timing', 'hold_state_only'].includes(r.processing) || r.check_exceptions.includes('timing_evidence')) && r.playback_start_seconds <= first && last < r.playback_end_seconds).map(r => r.id);
    if (allowed.length) exceptions.push({...record, exception_regions: allowed}); else warnings.push(record);
  });
  warnings.sort((a, b) => a.visible_start_seconds - b.visible_start_seconds || a.lane - b.lane);
  return {warnings, chart_exceptions: exceptions, accounted_observations: accounted, counts: {unaccounted_excluded_tracks: warnings.length, explicit_chart_exceptions: exceptions.length, already_represented_observations: accounted.length},
    reasons: counts(warnings, 'reason'), note: 'Warnings are excluded visible detections, not a verified count of missing chart notes. Noise candidates remain visible for review.'};
}

export function recognition(data: RecordData, ranges: RecordData): RecordData {
  const warnings = [], exceptions = [], accounted = [], regions = data.chart_policy?.regions ?? [];
  const add = (input, check = 'timing_evidence') => {
    const r = {observed_points: 0, ...input};
    const allowed = regions.filter(g => (g.check_exceptions.includes(check) || check === 'timing_evidence' && ['exclude_timing', 'hold_state_only'].includes(g.processing)) &&
      g.playback_start_seconds <= r.visible_start_seconds && r.visible_end_seconds < g.playback_end_seconds).map(g => g.id);
    (allowed.length ? exceptions : warnings).push({...r, ...(allowed.length ? {exception_regions: allowed} : {})});
  };
  const support = data.visual_support;
  const overview = {lane: 0, observed_points: 0, visible_start_seconds: data.start_seconds, visible_end_seconds: data.end_seconds};
  if (support && !support.chart_geometry) warnings.push({...overview, reason: 'unsupported_visual_profile', source_review: support});
  if (data.skin_detector && !data.skin_detector.registration_reviewed) warnings.push({...overview, reason: 'skin_registration_unverified', skin_contract: data.skin_detector.contract});
  if (data.skin_detector?.missing_template_roles?.length) warnings.push({...overview, reason: 'skin_template_coverage_incomplete', missing_template_roles: data.skin_detector.missing_template_roles});
  warnings.push(...(data.object_interpretation?.warnings ?? []));
  const effects = new Map<string, RecordData>((data.chart_policy?.gimmick_candidates ?? []).map(e => [e.id, e]));
  for (const id of data.chart_policy?.unsupported_gimmicks ?? []) {
    const e = effects.get(id);
    warnings.push({reason: 'chart_effect_handler_missing', check: 'chart_effect', lane: 0, observed_points: 0, gimmick_candidate: id, effect_kind: e.kind, visible_start_seconds: e.playback_start_seconds, visible_end_seconds: e.playback_end_seconds});
  }
  for (const key of ['timing_reconstruction', 'beat_timing', 'head_registration']) for (const r of data[key]?.warnings ?? []) add(r, 'timing_reconstruction');
  for (const [key, check] of [['skin_role_evidence', 'note_type_unresolved'], ['body_risk_evidence', 'note_processing_unresolved']]) for (const r of data[key]?.warnings ?? []) add(r, check);
  for (const r of data.visibility_diagnostics?.warnings ?? []) add(r, r.check);
  for (const r of data.note_type_diagnostics ?? []) add(r, r.reason);
  for (const role of data.hold_analysis?.observed_tail_roles ?? []) add({...role, note: role.tail_note, reason: 'observed_hold_tail_pending_geometry', observed_points: role.source_pts_seconds.length});
  const holds = [...(data.hold_analysis?.holds ?? []), ...(data.hold_analysis?.unresolved_holds ?? [])];
  for (const h of holds) {
    const lo = h.start_censored ? h.start_range[1] : h.start_range[0], hi = h.end_range ? h.end_range[1] : h.last_body_seconds;
    const base = {hold: h.id, lane: h.lane, visible_start_seconds: lo, visible_end_seconds: Math.max(lo, hi), observed_points: h.body_frames ?? 0};
    if (h.projection_failure) add({...base, reason: 'hold_chart_projection_failed', failure_detail: h.projection_failure}, 'timing_reconstruction');
    if (h.start_censored) add({...base, reason: 'hold_start_unresolved'});
    if (h.end_censored || !h.end_range) add({...base, reason: 'hold_end_unresolved'});
    for (const i of h.uncertain_components ?? []) add({...base, note: i, reason: 'hold_component_ownership_unresolved'});
  }
  for (const r of data.hold_analysis?.unresolved_tracks ?? []) {
    const c = r.cap_continuity ?? {}, gaps = c.gap_source_pts_seconds ?? [], seen = distinct(gaps) + distinct(c.connected_source_pts_seconds) + distinct(c.weak_source_pts_seconds);
    if (c.decision === 'disconnected_caps' && distinct(gaps) >= 8 && distinct(gaps) >= .8 * seen && c.visible_end_seconds - c.visible_start_seconds >= .12 &&
      ['head_note', 'tail_note'].every(k => data.notes[c[k]].status === 'estimated' && data.notes[c[k]].note_type !== 'hold')) {
      accounted.push({...r, interpretation: 'separate_caps_with_observed_gap'}); continue;
    }
    const owners = holds.filter(h => h.lane === r.lane && (r.cap_evidence ?? []).some(e => e.note === h[e.edge === 'top' ? 'head_note' : 'tail_note'] && distinct(e.source_pts_seconds) >= 4));
    if (owners.length === 1) accounted.push({...r, represented_by_hold: owners[0].id}); else add(r);
  }
  const matches = new Map(assignments(data).map(m => [m.note, m]));
  for (const [i, r] of entries<RecordData>(ranges.notes ?? {})) {
    const base = {note: i, lane: data.notes[i].lane, visible_start_seconds: r.target_range[0], visible_end_seconds: r.target_range[1], timing_status: r.status};
    if (!['matched', 'hold_state', 'policy_excluded'].includes(r.status)) add({...base, reason: 'timing_evidence_unresolved'});
    else if (r.status === 'matched' && !matches.get(i)?.judgment_label) add({...base, reason: 'judgment_label_unresolved'});
  }
  for (const e of processingEvidence(data)) {
    const i = e.note, n = data.notes[i];
    if (n.status !== 'estimated' || n.note_type === 'hold') continue;
    const conflict = matches.get(i)?.processing_conflict;
    if (e.status === 'unresolved' || conflict) add({note: i, lane: n.lane, visible_start_seconds: n.target_seconds, visible_end_seconds: n.target_seconds, observed_points: e.sample_count ?? (e.samples ?? []).length,
      reason: conflict ? 'processing_refresh_conflict' : 'note_processing_unresolved', processing_reason: e.reason, channel_evidence: e.id});
  }
  warnings.sort((a, b) => a.visible_start_seconds - b.visible_start_seconds || a.lane - b.lane || (a.reason < b.reason ? -1 : a.reason > b.reason ? 1 : 0));
  return {warnings, chart_exceptions: exceptions, accounted_hold_fragments: accounted, counts: counts(warnings, 'reason')};
}
