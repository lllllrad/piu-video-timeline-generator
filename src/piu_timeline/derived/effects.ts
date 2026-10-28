/** Apply concrete configured effects without modifying native observations. */
import {annotateMatches, bracket, onsetOverlaps, processingEvidence, processingSupport, receptorEvidence} from './evidence.ts';
import {associate} from './association.ts';
import type {RecordData} from './types.ts';
import {equal} from './math.ts';
const active = (data, kind) => (data.chart_policy?.gimmick_candidates ?? []).filter(e => e.kind === kind && e.review_status !== 'rejected');
const contains = (e, lo, hi) => e.playback_start_seconds <= lo && hi < e.playback_end_seconds;

export const FORMAT = {schema: 1, revision: 6};
export function verifyArtwork(data: RecordData): RecordData {
  const artifact = data.object_interpretation ?? {}, saved = artifact.effects ?? [], warnings = [];
  for (const effect of active(data, 'decorative_note_art')) {
    if (saved.some(record => Object.entries(effect).every(([k, v]) => equal(record[k], v)))) continue;
    warnings.push({reason: 'decorative_art_interpretation_missing', check: 'chart_effect', lane: 0,
      visible_start_seconds: effect.playback_start_seconds, visible_end_seconds: effect.playback_end_seconds, observed_points: 0, gimmick_candidate: effect.id});
  }
  return {...data, object_interpretation: {...artifact, warnings: [...(artifact.warnings ?? []), ...warnings]}};
}
export function interpret(data: RecordData): RecordData {
  let result = verifyArtwork(simultaneousIncrement(visibilityModifier(data)));
  if (result.chart_policy) result = {...result, chart_policy: {...result.chart_policy, gimmick_format: FORMAT,
    unsupported_gimmicks: (result.chart_policy.gimmick_candidates ?? []).filter(e => e.review_status !== 'rejected' &&
      !['scroll_pause', 'scroll_speed_change', 'suspected_visibility_modifier', 'suspected_multi_increment', 'decorative_note_art'].includes(e.kind)).map(e => e.id)}};
  return result;
}

export function visibilityModifier(data: RecordData): RecordData {
  const effects = active(data, 'suspected_visibility_modifier');
  if (!effects.length) return data;
  if (!data.visual_channels?.processing) throw new Error('Visibility modifier requires native processing evidence');
  const records = processingEvidence(data).map(original => {
    const owners = effects.filter(e => (data.visual_channels.processing.visibility_boundaries ?? []).some(b => b.notes.length && b.notes.includes(original.note) &&
      e.playback_start_seconds <= b.playback_range[0] && b.playback_range[1] <= e.playback_end_seconds + 1e-6));
    return original.reason === 'pre_receptor_visibility_boundary' && owners.length ? {...original, status: 'visibility_modified', reason: 'chart_visibility_modifier',
      gimmick_candidates: owners.map(e => e.id), native_status: original.status, native_reason: original.reason} : original;
  });
  const counts = {}; for (const r of records) counts[r.status] = (counts[r.status] ?? 0) + 1;
  return {...data, visual_channels: {...data.visual_channels, processing: {...data.visual_channels.processing, notes: records, counts}}};
}

export function simultaneousIncrement(data: RecordData): RecordData {
  const effects = active(data, 'suspected_multi_increment');
  if (!effects.length) return data;
  const events = (data.combo_events ?? []).map(e => ({...e})), adapted = new Map<number, RecordData | null>();
  events.forEach((e, i) => {
    const owners = effects.filter(o => contains(o, e.lower_seconds, e.upper_seconds)), increments = [...new Set(owners.map(o => o.combo_increment))];
    if (increments.length !== 1) {
      if (owners.length) { Object.assign(e, {gimmick_error: 'conflicting_simultaneous_increments', judged_row_count: null, status: 'excluded', reason: 'conflicting_simultaneous_increments'}); adapted.set(i, null); } return;
    }
    const increment = increments[0];
    if ((e.delta ?? 0) <= 1) return;
    Object.assign(e, {gimmick_candidates: owners.map(o => o.id), combo_increment: increment});
    if (e.delta !== increment || !(0 < e.upper_seconds - e.lower_seconds && e.upper_seconds - e.lower_seconds <= .1 + 1e-6)) {
      Object.assign(e, {judged_row_count: null, status: 'excluded', reason: 'counter_change_not_one_configured_increment', gimmick_error: 'counter_change_not_one_configured_increment'}); adapted.set(i, null);
    } else { Object.assign(e, {judged_row_count: 1, status: 'candidate', reason: null}); adapted.set(i, {...e, delta: 1}); }
  });
  if (!adapted.size) return {...data, combo_events: events};
  const matches = [];
  for (const m of data.matches ?? []) {
    if (!adapted.has(m.combo_event)) { matches.push({...m}); continue; }
    if (m.judgment_event != null) {
      const e = data.judgment_events[m.judgment_event], lo = e.lower_seconds, hi = e.upper_seconds, target = m.target_seconds;
      const kept = {...m, combo_event: null, evidence_source: 'judgment', observation_lower_seconds: lo, observation_upper_seconds: hi, raw_offset_lower_ms: 1000 * (lo - target), raw_offset_upper_ms: 1000 * (hi - target)};
      delete kept.combo_lower_seconds; delete kept.combo_upper_seconds; matches.push(kept);
    }
  }
  const matched = new Map<number, RecordData>(matches.map(m => [m.note, m])), missed = new Set((data.miss_candidates ?? []).map(m => m.note)), runs = receptorEvidence(data);
  const guard = 2 * (data.median_frame_interval_seconds || .017), proposals = [], indices = [], constraints = {};
  for (const [i, event] of adapted) {
    if (!event) continue;
    const lo = event.lower_seconds, hi = event.upper_seconds;
    if ((data.judgment_events ?? []).some(e => e.label === 'MISS' && e.lower_seconds <= hi + guard && e.upper_seconds >= lo - guard)) { Object.assign(events[i], {status: 'excluded', reason: 'competing_miss_evidence'}); continue; }
    const allowed = [];
    data.notes.forEach((n, ni) => {
      if (n.status !== 'estimated' || n.note_type === 'hold' || missed.has(ni) || (Object.hasOwn(n, 'prediction_uncertainty_seconds') ? n.prediction_uncertainty_seconds : 1) > .05) return;
      const h = data.hold_analysis ?? {};
      if ((h.holds ?? []).some(h => h.lane === n.lane && h.start_range[0] - guard <= hi && (h.end_range ? h.end_range[1] : h.last_body_seconds + .25) + guard >= lo)) return;
      if ((h.unresolved_tracks ?? []).some(t => t.lane === n.lane && t.visible_start_seconds - guard <= hi && t.visible_end_seconds + .25 + guard >= lo)) return;
      const existing = matched.get(ni);
      if (existing && !(lo <= (existing.observation_upper_seconds ?? -1) + guard && hi >= (existing.observation_lower_seconds ?? Infinity) - guard)) return;
      const onset = runs.filter(r => r.lane === n.lane && onsetOverlaps(r, lo, hi, guard));
      const owned = matches.some(m => m.note !== ni && data.notes[m.note].lane === n.lane && onset.length && onsetOverlaps(onset[0], bracket(m)[0] ?? -10, bracket(m)[1] ?? -10, guard));
      if (!owned && (onset.length === 1 || processingSupport(data, ni, lo, hi, guard))) allowed.push(ni);
    });
    constraints[proposals.length] = allowed; indices.push(i); proposals.push(event);
  }
  const recovered = associate(data.notes, proposals, .045, (data.display_delay_correction_ms ?? 0) / 1000, constraints);
  for (const m of recovered) {
    const index = indices[m.combo_event];
    Object.assign(m, {combo_event: index, combo_increment: events[index].combo_increment, recovery_method: 'configured_simultaneous_increment_with_lane_evidence', evidence_source: 'combo+lane_evidence'});
    const existing = matched.get(m.note);
    if (existing) Object.assign(existing, {combo_event: index, combo_lower_seconds: m.combo_lower_seconds, combo_upper_seconds: m.combo_upper_seconds, combo_increment: m.combo_increment, evidence_source: (existing.evidence_source ?? 'judgment') + '+configured_combo'});
    else { matches.push(m); matched.set(m.note, m); }
  }
  indices.forEach((index, local) => Object.assign(events[index], {status: proposals[local].status, reason: proposals[local].reason ?? null}));
  const coverage = {...data.coverage, timed_note_heads: matches.length, matched_combo_updates: new Set(matches.filter(m => m.combo_event != null).map(m => m.combo_event)).size,
    judgment_labeled_note_heads: matches.filter(m => m.judgment_label).length, unlabeled_timed_note_heads: matches.filter(m => !m.judgment_label).length};
  return annotateMatches({...data, combo_events: events, matches: matches.sort((a, b) => a.target_seconds - b.target_seconds), coverage});
}
