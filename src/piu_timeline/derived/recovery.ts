/** Recover exclusive rows from bounded visual evidence, preserving refresh bounds. */
import {candidates, targetInWindow, targetOffsets} from './candidates.ts';
import {bracket, disputedRefresh, onsetOverlaps, partition, processingSupport, receptorEvidence} from './evidence.ts';
import {boundedRefreshes} from './bounded_refresh.ts';
import {entries, median} from './math.ts';
import type {RecordData} from './types.ts';

export function holdOverlap(data, lo, hi, guard): boolean {
  const a = data.hold_analysis ?? {};
  if ((a.holds ?? []).some(h => h.start_range[0] - guard <= hi && (h.end_range ? h.end_range[1] : h.last_body_seconds + .25) + guard >= lo)) return true;
  if ((data.unsupported_intervals ?? []).some(r => r.start_seconds - guard <= hi && r.end_seconds + guard >= lo)) return true;
  const complete = h => h.head_note != null && h.tail_note != null && h.start_censored === false && h.end_censored === false && h.end_range && (h.body_frames ?? 0) >= 4 && ['skin_start_body_end_images', 'skin_temporal_image_regions'].includes(h.body_evidence);
  for (const t of a.unresolved_tracks ?? []) {
    if (data.native_body_risk_available && t.failure_detail === 'known_hold_image_connection_not_observed_in_clear_frames' && (a.holds ?? []).some(h => h.id != null && h.id === t.hold && h.head_note != null && h.head_note === t.note && h.tail_note != null && h.tail_note === t.tail_note && complete(h))) continue;
    if (data.native_body_risk_available && t.failure_detail === 'skin_body_images_without_complete_endpoint_ownership' && t.image_evidence?.length && t.image_evidence.every(p => p.role === 'hold_body')) continue;
    if (t.visible_start_seconds - guard <= hi && t.visible_end_seconds + .25 + guard >= lo) return true;
  }
  return false;
}

export function recoverAggregates(input: RecordData): [RecordData[], number[]] {
  const data = partition(input), notes = data.notes ?? [], original = data.matches ?? [], matched = new Map<number, RecordData>(original.map(m => [m.note, m]));
  const missed = new Set((data.miss_candidates ?? []).map(m => m.note)), runs = receptorEvidence(data), guard = 2 * (data.median_frame_interval_seconds || .017);
  const owned = new Map(), proposals = [], claims = new Map(), noteClaims = new Map();
  const claim = (map, key, id) => { if (!map.has(key)) map.set(key, new Set()); map.get(key).add(id); };
  for (const m of original) {
    const [lo, hi] = bracket(m); if (lo == null || hi == null) continue;
    runs.forEach((r, ri) => { if (r.lane === notes[m.note].lane && onsetOverlaps(r, lo, hi, guard)) claim(owned, ri, m.note); });
  }
  (data.combo_events ?? []).forEach((e, ei) => {
    const lo = e.lower_seconds, hi = e.upper_seconds, count = e.delta ?? 0;
    if (!(2 <= count && count <= 10 && 0 < hi - lo && hi - lo <= .1 + 1e-6) || ['combo_reset', 'combo_jump_or_observation_gap'].includes(e.reason) || holdOverlap(data, lo, hi, guard)) return;
    if ((data.judgment_events ?? []).some(w => w.label === 'MISS' && w.lower_seconds <= hi + guard && w.upper_seconds >= lo - guard)) return;
    const anchors = original.filter(m => Math.abs(m.target_seconds - (lo + hi) / 2) < 1 && bracket(m).every(t => t != null));
    const local = anchors.length ? median(anchors.map(m => (bracket(m)[0] + bracket(m)[1]) / 2 - m.target_seconds)) : (data.display_delay_correction_ms ?? 0) / 1000;
    const offsets = targetOffsets(data, local), correction = (data.display_delay_correction_ms ?? 0) / 1000;
    const plausible = notes.flatMap((n, i) => n.status === 'estimated' && n.note_type !== 'hold' && offsets.some(o => targetInWindow(n, lo, hi, o)) && n.target_seconds + correction - .25 <= hi && n.target_seconds + correction + .5 >= lo ? [[i, n]] : [])
      .sort((a, b) => a[1].target_seconds - b[1].target_seconds), rows = [];
    for (const [i, n] of plausible) {
      if (rows.length && n.target_seconds - notes[rows.at(-1)[0]].target_seconds < .025) rows.at(-1).push(i); else rows.push([i]);
    }
    if (rows.length !== count || rows.some(r => r.length !== 1)) return;
    const group = rows.map(r => r[0]);
    if (group.some(i => disputedRefresh(data, i, [{...e, source: 'combo', event: ei}])) || !offsets.some(o => group.every(i => targetInWindow(notes[i], lo, hi, o))) || group.some(i => notes[i].prediction_uncertainty_seconds > .05)) return;
    if (original.some(m => !group.includes(m.note) && bracket(m).every(t => t != null) && bracket(m)[0] < hi && bracket(m)[1] > lo)) return;
    if (group.every(i => matched.has(i)) || group.some(i => missed.has(i))) return;
    if (group.some(i => { const m = matched.get(i); return m && (m.combo_event != null && m.combo_event !== ei || bracket(m)[0] > hi || bracket(m)[1] < lo); })) return;
    if (original.some(m => m.combo_event === ei && !group.includes(m.note))) return;
    const proofs = {};
    for (const i of group) {
      const ids = runs.flatMap((r, ri) => r.lane === notes[i].lane && onsetOverlaps(r, lo, hi, guard) ? [ri] : []);
      if (ids.length !== 1) return; proofs[i] = ids[0];
    }
    if (new Set(Object.values(proofs)).size !== group.length || entries<number>(proofs).some(([i, ri]) => [...(owned.get(ri) ?? [])].some(id => id !== i))) return;
    proposals.push({ei, group, proofs, offsets});
    for (const [i, ri] of entries(proofs)) { claim(claims, ri, ei); claim(noteClaims, i, ei); }
  });
  const result = new Map<number, RecordData>(original.map(m => [m.note, {...m}])), recovered = [];
  for (const {ei, group, proofs, offsets} of proposals) {
    if (entries(proofs).some(([i, ri]) => claims.get(ri).size !== 1 || noteClaims.get(i).size !== 1)) continue;
    const event = data.combo_events[ei], lo = event.lower_seconds, hi = event.upper_seconds;
    for (const i of group) {
      const run = runs[proofs[i]], common = {combo_event: ei, combo_lower_seconds: lo, combo_upper_seconds: hi,
        aggregate_body_risk_basis: data.native_body_risk_available ? 'native_receptor_body_regions' : 'hold_geometry_and_unresolved_tracks', aggregate_target_offset_hypotheses_seconds: offsets,
        aggregate_row_count: event.delta, aggregate_lane_onset_range: run.onset_range ?? null, aggregate_lane_onset_source_pts_seconds: run.onset_source_pts_seconds ?? null, aggregate_evidence_method: 'exclusive_tap_onsets_for_complete_counter_increment'};
      if (result.has(i)) {
        const m = result.get(i); Object.assign(m, common); m.evidence_source = 'combo+lane_onset' + (m.judgment_event != null || m.judgment_label ? '+judgment' : ''); continue;
      }
      const target = notes[i].target_seconds;
      result.set(i, {...common, note: i, target_seconds: target, row_note_count: 1, judgment_event: null, evidence_source: 'combo+lane_onset', recovery_method: 'aggregate_counter_with_exclusive_lane_onsets',
        observation_lower_seconds: lo, observation_upper_seconds: hi, raw_offset_lower_ms: (lo - target) * 1000, raw_offset_upper_ms: (hi - target) * 1000}); recovered.push(i);
    }
  }
  return [[...result.values()].sort((a, b) => a.target_seconds - b.target_seconds), recovered];
}

export function recoverRows(input: RecordData): [RecordData[], number[]] {
  const data = partition(input), matches = [...(data.matches ?? [])], notes = data.notes ?? [];
  if (matches.some(m => !Object.hasOwn(m, 'target_seconds')) || notes.some(n => n.status === 'estimated' && !Object.hasOwn(n, 'prediction_uncertainty_seconds'))) return [matches, []];
  const guard = 2 * (data.median_frame_interval_seconds || .017), runs = receptorEvidence(data), events = [];
  for (const [source, key] of [['combo', 'combo_events'], ['judgment', 'judgment_events']]) (data[key] ?? []).forEach((e, index) => {
    const lo = e.lower_seconds, hi = e.upper_seconds;
    if (!(0 <= hi - lo && hi - lo <= .12) || (Object.hasOwn(e, 'delta') ? e.delta : 1) !== 1 || source === 'judgment' && !['PERFECT', 'GREAT', 'GOOD', 'BAD'].includes(e.label) || e.detection_status === 'excluded') return;
    events.push({source, event: index, delta: 1, lower_seconds: lo, upper_seconds: hi, reason: e.reason ?? null});
  });
  const [choices] = candidates(data, events), assigned = new Set(matches.map(m => m.note)), missed = new Set((data.miss_candidates ?? []).map(c => c.note));
  const eligible = notes.flatMap((n, i) => n.status === 'estimated' && n.note_type !== 'hold' && !assigned.has(i) && !missed.has(i) ? [[i, n]] : []);
  const owned = new Map<string, Set<number>>(), eventRows = new Map<string, number[]>(), proposals = [];
  const own = (key, i) => { if (!owned.has(key)) owned.set(key, new Set()); owned.get(key).add(i); };
  for (const m of matches) {
    const [lo, hi] = bracket(m); if (lo == null || hi == null) continue;
    runs.forEach((r, ri) => { if (r.lane === notes[m.note].lane && onsetOverlaps(r, lo, hi, guard)) own(String(ri), m.note); });
  }
  for (const [ni, all] of entries(choices)) {
    const options = all.filter(o => o.alternative_rows === 1 && o.aggregate_row_capacity === 1 && targetOffsets(data, o.ranking_offset_seconds).some(offset => targetInWindow(notes[ni], o.lower_seconds, o.upper_seconds, offset)));
    if (!options.length || Math.max(...options.map(o => o.upper_seconds)) - Math.min(...options.map(o => o.upper_seconds)) > (data.median_frame_interval_seconds || .017) + .002) continue;
    const supported = [];
    for (const o of options) {
      const lo = o.lower_seconds, hi = o.upper_seconds, offsets = targetOffsets(data, o.ranking_offset_seconds);
      const plausible = eligible.filter(([, n]) => n.lane === notes[ni].lane && offsets.some(offset => targetInWindow(n, lo, hi, offset))).map(([i]) => i);
      if (plausible.length !== 1 || plausible[0] !== ni) continue;
      const ids = runs.flatMap((r, ri) => r.lane === notes[ni].lane && onsetOverlaps(r, lo, hi, guard) ? [ri] : []);
      if (ids.length === 1) supported.push([o, String(ids[0])]);
      else if (!ids.length && processingSupport(data, ni, lo, hi, guard)) supported.push([o, `processing:${ni}`]);
    }
    if (!supported.length || new Set(supported.map(p => p[1])).size !== 1) continue;
    const ri = supported[0][1]; own(ri, ni); proposals.push({ni, supported, ri});
    for (const [o] of supported) { const key = `${o.source},${o.event}`; if (!eventRows.has(key)) eventRows.set(key, []); eventRows.get(key).push(notes[ni].target_seconds); }
  }
  const recovered = [];
  for (const {ni, supported, ri} of proposals) {
    if (owned.get(ri).size !== 1 || !owned.get(ri).has(ni) || supported.some(([o]) => { const rows = eventRows.get(`${o.source},${o.event}`); return Math.max(...rows) - Math.min(...rows) >= .025; })) continue;
    const [o] = [...supported].sort((a, b) => (a[0].upper_seconds - a[0].lower_seconds) - (b[0].upper_seconds - b[0].lower_seconds) || (a[0].source < b[0].source ? -1 : a[0].source > b[0].source ? 1 : 0))[0];
    const target = notes[ni].target_seconds, processing = ri.startsWith('processing:');
    const m: RecordData = {note: ni, target_seconds: target, row_note_count: 1, aggregate_row_count: 1, combo_event: null, judgment_event: null,
      evidence_source: o.source + (processing ? '+note_disappearance' : '+lane_onset'), observation_lower_seconds: o.lower_seconds, observation_upper_seconds: o.upper_seconds,
      raw_offset_lower_ms: (o.lower_seconds - target) * 1000, raw_offset_upper_ms: (o.upper_seconds - target) * 1000,
      recovery_method: processing ? 'unique_row_with_note_disappearance' : 'unique_row_with_independent_lane_onset'};
    if (processing) { const p = processingSupport(data, ni, o.lower_seconds, o.upper_seconds, guard); Object.assign(m, {processing_range: p.range, processing_source_pts_seconds: p.source_pts_seconds}); }
    else { const r = runs[Number(ri)]; Object.assign(m, {lane_onset_range: r.onset_range ?? null, lane_onset_source_pts_seconds: r.onset_source_pts_seconds ?? null}); }
    for (const [option] of supported) {
      m[option.source === 'combo' ? 'combo_event' : 'judgment_event'] = option.event;
      if (option.source === 'combo') { const e = data.combo_events[option.event]; Object.assign(m, {combo_lower_seconds: e.lower_seconds, combo_upper_seconds: e.upper_seconds}); }
      else m.judgment_label = data.judgment_events[option.event].label;
    }
    matches.push(m); recovered.push(ni);
  }
  for (const m of matches) if (recovered.includes(m.note)) m.row_note_count = matches.filter(other => Math.abs(other.target_seconds - m.target_seconds) < .025 &&
    (m.combo_event != null && other.combo_event === m.combo_event || m.judgment_event != null && other.judgment_event === m.judgment_event)).length;
  const [result, aggregated] = recoverAggregates({...data, matches});
  // Conditional clock evidence cannot displace an independently supported row.
  const pending=partition({...data,matches:result}),[remaining]=candidates(pending,events);
  const bounded=boundedRefreshes(pending,remaining,events,(lo,hi)=>holdOverlap(pending,lo,hi,guard));
  return [[...result,...bounded], [...recovered, ...aggregated,...bounded.map(m=>m.note)]];
}
