import {associate, synchronizedRefreshes} from './association.ts';
import {assignments, bracket, disputedRefresh, partition} from './evidence.ts';
import {lowerBound, upperBound} from './math.ts';
import type {RecordData} from './types.ts';

export function attachRecoveredLabels(input: RecordData): RecordData {
  const data = partition(input), matches = data.matches.map(m => ({...m})), words = (data.judgment_events ?? []).map(e => ({...e})), counters = (data.combo_events ?? []).map(e => ({...e}));
  if (!words.length || !counters.length) return {...data, matches, judgment_events: words};
  const groups = new Map<number, RecordData[]>(), owners = new Map<number, RecordData[]>(), eligible = new Set();
  for (const m of matches) for (const [key, map] of [['combo_event', groups], ['judgment_event', owners]] as const) if (m[key] != null) {
    if (!map.has(m[key])) map.set(m[key], []); map.get(m[key]).push(m);
  }
  for (const [ci, group] of groups) {
    const c = counters[ci];
    if (c.delta !== 1 || !group.some(m => m.recovery_method) || !group.some(m => !m.judgment_label) ||
      Math.max(...group.map(m => m.target_seconds)) - Math.min(...group.map(m => m.target_seconds)) >= .025 || group.some(m => (m.aggregate_row_count ?? 1) !== 1) || c.detection_status === 'excluded') continue;
    if (c.status !== 'matched' && !['possible_hold_or_dense_stack', 'ambiguous_note_or_combo_association', 'ongoing_hold_tick_not_new_press'].includes(c.reason)) continue;
    c.status = 'matched'; eligible.add(ci);
  }
  const candidates = words.map(e => ({...e, status: ['PERFECT', 'GREAT', 'GOOD', 'BAD'].includes(e.label) ? (Object.hasOwn(e, 'detection_status') ? e.detection_status : 'candidate') : 'excluded'}));
  for (const [ji, ci] of synchronizedRefreshes({combo_events: counters}, candidates)) {
    if (!eligible.has(ci)) continue;
    const group = groups.get(ci), word = words[ji];
    if ((owners.get(ji) ?? []).some(m => m.combo_event !== ci) || word.anchor_combo_event != null && word.anchor_combo_event !== ci ||
      group.some(m => m.judgment_event != null && m.judgment_event !== ji || m.judgment_label != null && m.judgment_label !== word.label)) continue;
    Object.assign(word, {status: 'corroborating', reason: null, anchor_combo_event: ci});
    for (const m of group) if (!m.judgment_label) {
      const source = m.evidence_source ?? 'combo';
      Object.assign(m, {judgment_label: word.label, judgment_event: ji, judgment_label_source: 'recovered_synchronized_refresh', evidence_source: source.split('+').includes('judgment') ? source : source + '+judgment'});
    }
  }
  return {...data, matches, judgment_events: words};
}

export function recoverPreHold(input: RecordData, notes: RecordData[], original: RecordData[], suppressed: number[], proofs: Record<string, RecordData>): [RecordData[], number[]] {
  const data = partition({...input, matches: original}), matches = data.matches;
  if (!data.native_body_risk_available) return [matches, []];
  const assigned = new Set([...matches.map(m => m.note), ...(data.miss_candidates ?? []).map(c => c.note), ...suppressed]);
  const owned = new Set(matches.map(m => m.judgment_event)), guard = 2 * (data.median_frame_interval_seconds || .017), candidates = [], safe = {}, constraints = {};
  const anchors = matches.filter(m => bracket(m).every(t => t != null)).map(m => [m, bracket(m)] as const);
  (data.judgment_events ?? []).forEach((e, index) => {
    const lo = e.lower_seconds, hi = e.upper_seconds;
    const native = e.detection_status === 'candidate' && (Object.hasOwn(e, 'delta') ? e.delta : 1) === 1 && ['PERFECT', 'GREAT', 'GOOD', 'BAD'].includes(e.label) && 0 < hi - lo && hi - lo <= .1 + 1e-6;
    const occupied = owned.has(index) || anchors.some(([, [a, b]]) => a <= hi + guard && b >= lo - guard);
    candidates.push({...e, status: native && !occupied ? 'candidate' : 'excluded'});
    if (!native || occupied) return;
    const lower = Math.max(-Infinity, ...anchors.filter(([, [, b]]) => b < lo).map(([m]) => m.target_seconds)), upper = Math.min(Infinity, ...anchors.filter(([, [a]]) => a > hi).map(([m]) => m.target_seconds));
    constraints[index] = notes.flatMap((n, i) => n.status === 'estimated' && !assigned.has(i) && lower < n.target_seconds && n.target_seconds < upper ? [i] : []);
    if (e.reason === 'possible_hold_or_dense_stack' && proofs[index]) safe[index] = proofs[index];
  });
  if (!Object.keys(safe).length) return [matches, []];
  const eligible = notes.map((n, i) => assigned.has(i) ? {...n, status: 'excluded'} : n), proposals = associate(eligible, candidates, .045, (data.display_delay_correction_ms ?? 0) / 1000, constraints);
  const result = [...matches], recovered = [];
  for (const p of proposals) {
    const i = p.note, ei = p.combo_event;
    if (!safe[ei] || notes[i].type_status !== 'tap' || notes[i].note_type === 'hold') continue;
    const e = data.judgment_events[ei], target = notes[i].target_seconds;
    if (disputedRefresh(data, i, [{...e, source: 'judgment', event: ei}])) continue;
    const lo = e.lower_seconds, hi = e.upper_seconds;
    result.push({note: i, target_seconds: target, row_note_count: p.row_note_count, aggregate_row_count: 1, combo_event: null, judgment_event: ei, evidence_source: 'judgment', judgment_label: e.label,
      judgment_label_source: 'native_refresh_before_accounted_hold', observation_lower_seconds: lo, observation_upper_seconds: hi, raw_offset_lower_ms: (lo - target) * 1000, raw_offset_upper_ms: (hi - target) * 1000,
      recovery_method: 'strict_judgment_before_accounted_hold', hold_risk_accounting: safe[ei]}); recovered.push(i);
  }
  return [result, recovered];
}

export function labelCounterFrames(data: RecordData, observations: RecordData[]): RecordData {
  data.counter_judgment_labels = {};
  if (!observations.length) return data;
  const times = observations.map(f => f.playback_seconds), groups = new Map<number, RecordData[]>((data.combo_events ?? []).map((_, i) => [i, []]));
  for (const m of data.matches) if (m.combo_event != null) { if (!groups.has(m.combo_event)) groups.set(m.combo_event, []); groups.get(m.combo_event).push(m); }
  let count = 0;
  for (const [ci, group] of groups) {
    const e = data.combo_events[ci];
    if (e.delta !== 1 || e.upper_seconds - e.lower_seconds > .1 + 1e-6) continue;
    const start = e.upper_seconds, stop = Math.min(start + .050001, ci + 1 < data.combo_events.length ? data.combo_events[ci + 1].lower_seconds - 1e-6 : Infinity);
    const frames = observations.slice(lowerBound(times, start - 1e-6), upperBound(times, stop)), labels = new Set(frames.filter(f => f.label != null).map(f => f.label));
    const known = frames.filter(f => f.label != null && f.confidence >= .8);
    if (labels.size !== 1 || labels.has('MISS') || known.length < 2 || known[0].playback_seconds > start + .035 || !known.slice(1).some((b, i) => b.playback_seconds - known[i].playback_seconds <= .035) || new Set(known.map(f => f.source_pts_seconds)).size < 2) continue;
    const proof = {label: known[0].label, observations: known.map(f => Object.fromEntries(['source_pts_seconds', 'playback_seconds', 'label', 'confidence'].map(k => [k, f[k]])))};
    data.counter_judgment_labels[ci] = proof;
    for (const m of group) if (!m.judgment_label) {
      Object.assign(m, {evidence_source: 'combo+judgment', judgment_label: known[0].label, judgment_event: null, judgment_label_source: 'post_combo_frames', judgment_observations: proof.observations.map(o => ({...o}))}); count++;
    }
  }
  data.coverage.combo_frame_labeled_note_heads = count;
  return data;
}

export function mergeJudgments(data: RecordData, inputEvents: RecordData[], observations: RecordData[] = []): RecordData {
  const events = structuredClone(inputEvents);
  for (const e of events) {
    delete e.anchor_combo_event;
    Object.assign(e, {status: Object.hasOwn(e, 'detection_status') ? e.detection_status : 'candidate', reason: e.detection_reason ?? null});
    if (e.label === 'MISS') Object.assign(e, {status: 'excluded', reason: 'miss_is_not_a_press_timestamp'});
    else if ((data.unsupported_intervals ?? []).some(r => e.upper_seconds >= r.start_seconds - .1 && e.lower_seconds <= r.end_seconds + .1)) Object.assign(e, {status: 'excluded', reason: 'possible_hold_or_dense_stack'});
  }
  const source = assignments(data).sort((a, b) => (a.target_seconds ?? data.notes[a.note]?.target_seconds ?? Infinity) - (b.target_seconds ?? data.notes[b.note]?.target_seconds ?? Infinity) || a.note - b.note);
  const matches = source.filter(m => m.combo_event != null), comboMatches = [...matches], byNote = new Map(matches.map(m => [m.note, m])), counterGroups = new Map<number, RecordData[]>();
  for (const m of matches) {
    Object.assign(m, {evidence_source: 'combo', observation_lower_seconds: m.combo_lower_seconds, observation_upper_seconds: m.combo_upper_seconds});
    for (const key of ['judgment_label', 'judgment_event', 'judgment_label_source', 'judgment_observations']) delete m[key];
    if (!counterGroups.has(m.combo_event)) counterGroups.set(m.combo_event, []); counterGroups.get(m.combo_event).push(m);
  }
  const anchors = [], anchored = new Set();
  for (const [ji, ci] of synchronizedRefreshes(data, events)) {
    const group = counterGroups.get(ci); if (!group?.length) continue;
    const e = events[ji]; Object.assign(e, {status: 'corroborating', reason: null, anchor_combo_event: ci});
    for (const m of group) Object.assign(m, {evidence_source: 'combo+judgment', judgment_label: e.label, judgment_event: ji, judgment_label_source: 'synchronized_refresh'});
    anchors.push([ji, group.map(m => m.note)]); anchored.add(ci);
  }
  const constraints = {};
  events.forEach((e, ji) => {
    if (e.status !== 'candidate') return;
    const before = anchors.filter(([i]) => i < ji).flatMap(([, ids]) => ids.map(n => data.notes[n].target_seconds)), after = anchors.filter(([i]) => i > ji).flatMap(([, ids]) => ids.map(n => data.notes[n].target_seconds));
    const low = Math.max(-Infinity, ...before), high = Math.min(Infinity, ...after);
    constraints[ji] = data.notes.flatMap((n, i) => n.status === 'estimated' && low < n.target_seconds && n.target_seconds < high ? [i] : []);
  });
  const judged = associate(data.notes, events, .045, (data.display_delay_correction_ms ?? 0) / 1000, constraints), groups = new Map<number, RecordData[]>();
  for (const m of judged) { if (!groups.has(m.combo_event)) groups.set(m.combo_event, []); groups.get(m.combo_event).push(m); }
  const constituent = (ci, ids, e) => {
    const c = data.combo_events[ci], members = counterGroups.get(ci) ?? [];
    if ((c.delta ?? 1) <= 1 || ![...ids].every(id => members.some(m => m.note === id)) || !(0 < c.upper_seconds - c.lower_seconds && c.upper_seconds - c.lower_seconds <= .1 + 1e-6)) return false;
    const rows = [];
    for (const t of members.map(m => m.target_seconds).sort((a, b) => a - b)) if (!rows.length || t - rows.at(-1) >= .025) rows.push(t);
    return rows.length === c.delta && e.upper_seconds >= c.lower_seconds - 1e-6 && e.lower_seconds <= c.upper_seconds + 1e-6;
  };
  for (const [index, group] of groups) {
    const e = events[index], ids = new Set(group.map(m => m.note));
    const conflicting = comboMatches.some(m => !ids.has(m.note) && !anchored.has(m.combo_event) && !constituent(m.combo_event, ids, e) && e.lower_seconds - .025 <= m.combo_upper_seconds && e.upper_seconds + .025 >= m.combo_lower_seconds);
    if (conflicting) { Object.assign(e, {status: 'excluded', reason: 'competing_combo_evidence'}); continue; }
    for (const m of group) {
      const existing = byNote.get(m.note);
      if (existing) { Object.assign(existing, {evidence_source: 'combo+judgment', judgment_label: e.label, judgment_event: index, judgment_label_source: 'aligned_refresh'}); e.status = 'corroborating'; }
      else {
        Object.assign(m, {combo_event: null, judgment_event: index, judgment_label: e.label, evidence_source: 'judgment', observation_lower_seconds: m.combo_lower_seconds, observation_upper_seconds: m.combo_upper_seconds});
        delete m.combo_lower_seconds; delete m.combo_upper_seconds; matches.push(m);
      }
    }
  }
  const used = new Set(matches.map(m => m.note)), misses = [];
  events.forEach((e, i) => {
    if (e.label !== 'MISS') return;
    const candidates = data.notes.flatMap((n, ni) => n.status === 'estimated' && !used.has(ni) && e.lower_seconds - .25 <= n.target_seconds && n.target_seconds <= e.upper_seconds ? [ni] : []);
    if (candidates.length && Math.max(...candidates.map(i => data.notes[i].target_seconds)) - Math.min(...candidates.map(i => data.notes[i].target_seconds)) < .025) for (const n of candidates) {
      misses.push({note: n, judgment_event: i, label: 'MISS', status: 'possible_miss', input_seconds: null}); used.add(n);
    }
  });
  Object.assign(data, {matches: matches.sort((a, b) => a.target_seconds - b.target_seconds), judgment_events: events, miss_candidates: misses, coverage: {...data.coverage, combo_frame_labeled_note_heads: 0}});
  labelCounterFrames(data, observations);
  Object.assign(data.coverage, {timed_note_heads: matches.length, judgment_labeled_note_heads: matches.filter(m => m.judgment_label).length, unlabeled_timed_note_heads: matches.filter(m => !m.judgment_label).length,
    judgment_only_note_heads: matches.filter(m => m.evidence_source === 'judgment').length, observed_judgment_updates: events.length, observed_miss_updates: events.filter(e => e.label === 'MISS').length});
  return data;
}
