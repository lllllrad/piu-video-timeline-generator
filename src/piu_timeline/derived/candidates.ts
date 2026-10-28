import {median} from './math.ts';
import {afterRefresh, bracket, disputedRefresh, onsetOverlaps, partition, processingConflicts, processingEvidence, processingSupport, receptorEvidence} from './evidence.ts';
import type {Interval, RecordData} from './types.ts';
export const EARLY = .25, LATE = .5;
export const targetOffsets = (data, local) => [...new Set<number>([(data.display_delay_correction_ms ?? 0) / 1000, local])].sort((a, b) => a - b);
export const targetInWindow = (note, lo, hi, offset) => lo - .045 - note.prediction_uncertainty_seconds <= note.target_seconds + offset && note.target_seconds + offset <= hi + .045 + note.prediction_uncertainty_seconds;
export const associationWindow = (note, correction = 0): Interval => [note.target_seconds + correction - EARLY, note.target_seconds + correction + LATE];
export function intersectWindow(a: number[], b: number[]): Interval | null { const lo = Math.max(a[0], b[0]), hi = Math.min(a[1], b[1]); return lo <= hi ? [lo, hi] : null; }

export function candidates(input: RecordData, events: RecordData[]): [Record<string, RecordData[]>, Record<string, string[]>] {
  const data = partition(input), notes = data.notes ?? [], matches = data.matches ?? [], correction = (data.display_delay_correction_ms ?? 0) / 1000;
  const frame = data.median_frame_interval_seconds || .017, lit = {}, unknown = {}, sensor = {};
  if (notes.some(n => n.status === 'estimated' && [n.target_seconds, n.prediction_uncertainty_seconds].some(v => typeof v !== 'number' || !Number.isFinite(v)))) throw new Error('Candidate rows require bounded native timing');
  for (const run of receptorEvidence(data)) {
    const lane = run.lane;
    if (run.lit == null) { (unknown[lane] ??= []).push(run); continue; }
    sensor[lane] ??= [0, 0]; sensor[lane][Number(Boolean(run.lit))] += run.frames;
    if (run.lit) (lit[lane] ??= []).push(run);
  }
  const anchors = [], owners = new Map<string, RecordData[]>();
  for (const match of matches) {
    const [lo, hi] = bracket(match);
    if (lo == null || hi == null) continue;
    const anchor = {lo, hi, target: match.target_seconds, note: match.note}; anchors.push(anchor);
    for (const source of ['combo', 'judgment']) if (match[`${source}_event`] != null) {
      const key = `${source},${match[`${source}_event`]}`;
      if (!owners.has(key)) owners.set(key, []); owners.get(key).push(anchor);
    }
  }
  const assigned = new Set(matches.map(m => m.note)), missed = new Set((data.miss_candidates ?? []).map(c => c.note));
  const eligible = notes.flatMap((n, i) => n.status === 'estimated' && n.note_type !== 'hold' && !assigned.has(i) && !missed.has(i) ? [[i, n]] : []).sort((a, b) => a[1].target_seconds - b[1].target_seconds);
  const families = [];
  for (const event of [...events].sort((a, b) => a.upper_seconds - b.upper_seconds || a.lower_seconds - b.lower_seconds)) {
    const family = [...families.slice(-4)].reverse().find(f => Math.abs(f.hi - event.upper_seconds) <= frame + .002 && event.lower_seconds <= f.hi + .01 && f.events.every(e => e.source !== event.source));
    if (!family) families.push({lo: event.lower_seconds, hi: event.upper_seconds, events: [event]});
    else { family.events.push(event); family.lo = Math.min(family.lo, event.lower_seconds); family.hi = Math.max(family.hi, event.upper_seconds); }
  }
  const result = {}, rejected: Record<string, Set<string>> = {}, reject = (i, reason) => (rejected[i] ??= new Set()).add(reason);
  for (const family of families) {
    const {lo, hi} = family;
    let owned = family.events.flatMap(e => owners.get(`${e.source},${e.event}`) ?? []);
    if (!owned.length) owned = anchors.filter(a => Math.abs(a.hi - hi) <= frame + .002 && a.lo <= hi && a.hi >= lo);
    const previous = anchors.filter(a => a.hi < lo - .01).sort((a, b) => b.hi - a.hi)[0], following = anchors.filter(a => a.lo > hi + .01).sort((a, b) => a.lo - b.lo)[0];
    const nearby = anchors.filter(a => Math.abs((a.lo + a.hi) / 2 - (lo + hi) / 2) < 1);
    const offset = nearby.length ? median(nearby.map(a => (a.lo + a.hi) / 2 - a.target)) : correction, rows = [], supports = {};
    for (const [index, note] of eligible) {
      if (disputedRefresh(data, index, family.events)) { reject(index, 'refresh_conflicts_with_note_processing'); continue; }
      const target = note.target_seconds, uncertainty = note.prediction_uncertainty_seconds, overlap = intersectWindow([lo, hi], associationWindow(note, correction));
      if (!overlap) { reject(index, 'outside_association_window'); continue; }
      const [supportLo, supportHi] = overlap;
      if (processingEvidence(data).some(p => p.note === index && afterRefresh(p, supportHi, frame * 2))) { reject(index, 'head_observed_after_refresh'); continue; }
      if (processingConflicts(data, index, supportLo, supportHi, frame * 2)) { reject(index, 'contradicts_observed_note_disappearance'); continue; }
      const lane = note.lane;
      if (owned.length && owned.some(o => Math.abs(o.target - target) > .025 || notes[o.note].lane === lane)) { reject(index, 'refresh_already_assigned_to_another_row'); continue; }
      if (previous && target < previous.target - .025 || following && target > following.target + .025) { reject(index, 'violates_processed_row_order'); continue; }
      const reliable = Math.min(...(sensor[lane] ?? [0, 0])) >= 3;
      const supported = (lit[lane] ?? []).filter(r => r.frames >= 2 && r.start_seconds <= supportHi + frame * 2 && r.end_seconds >= supportLo - frame * 2 || onsetOverlaps(r, supportLo, supportHi, frame * 2));
      const obscured = (unknown[lane] ?? []).some(r => r.start_seconds <= supportHi && r.end_seconds >= supportLo), processing = processingSupport(data, index, supportLo, supportHi, frame * 2);
      if (reliable && !supported.length && !obscured && !processing) { reject(index, 'receptor_lane_not_active'); continue; }
      supports[index] = supported;
      const holdTick = family.events.some(e => e.reason === 'ongoing_hold_tick_not_new_press') || (data.hold_analysis?.holds ?? []).some(h =>
        hi >= (h.start_censored ? h.start_range[1] : (h.start_range[0] + h.start_range[1]) / 2) + .04 && lo <= (h.end_range ? (h.end_range[0] + h.end_range[1]) / 2 : h.last_body_seconds));
      if (holdTick && !processing && !supported.some(r => onsetOverlaps(r, supportLo, supportHi, frame * 2))) { reject(index, 'hold_tick_without_independent_lane_onset'); continue; }
      const distance = Math.max(0, Math.abs(target + offset - (lo + hi) / 2) - (hi - lo) / 2 - uncertainty);
      if (rows.length && Math.abs(target - rows.at(-1).target) < .025) { rows.at(-1).notes.push(index); rows.at(-1).cost = Math.min(rows.at(-1).cost, distance); rows.at(-1).uncertainty = Math.max(rows.at(-1).uncertainty, uncertainty); }
      else rows.push({target, notes: [index], cost: distance, uncertainty});
    }
    if (!rows.length) continue;
    const best = Math.min(...rows.map(r => r.cost)), capacity = Math.max(...family.events.map(e => e.delta ?? 1));
    let selected = rows.filter(r => r.cost <= best + Math.max(.008, frame / 2));
    if (capacity > 1) {
      const center = [...rows].sort((a, b) => a.cost - b.cost)[0].target;
      selected.push(...rows.filter(r => !selected.includes(r) && Math.abs(r.target - center) <= hi - lo + .02));
      selected = selected.sort((a, b) => a.cost - b.cost).slice(0, capacity);
    }
    const sourceCost = (r, e) => Math.max(0, Math.abs(r.target + offset - (e.lower_seconds + e.upper_seconds) / 2) - (e.upper_seconds - e.lower_seconds) / 2 - r.uncertainty);
    const sourceRows = new Map<RecordData, RecordData[]>();
    for (const event of family.events) {
      const plausible = ((event.delta ?? 1) === 1 ? rows : selected).filter(row =>
        row.notes.some(index => intersectWindow([event.lower_seconds, event.upper_seconds], associationWindow(notes[index], correction))));
      const best = Math.min(...plausible.map(row => sourceCost(row, event)));
      sourceRows.set(event, plausible.filter(row => (event.delta ?? 1) !== 1 || sourceCost(row, event) <= best + Math.max(.008, frame / 2)));
    }
    const usedRows = new Set([...sourceRows.values()].flat());
    for (const row of rows) if (!usedRows.has(row)) row.notes.forEach(i => reject(i, 'another_note_row_is_better_supported'));
    for (const event of family.events) for (const row of sourceRows.get(event)) for (const index of row.notes) {
      const window = associationWindow(notes[index], correction), range = intersectWindow([event.lower_seconds, event.upper_seconds], window);
      if (!range) continue;
      (result[index] ??= []).push({...event, candidate_range: range, association_window: window, constraints: ['hard_timing_window', 'event_ownership', 'processed_row_order', 'closest_row'],
        processing_evidence: processingSupport(data, index, range[0], range[1], frame * 2), lane_receptor_support: !!supports[index].length, lane_support_runs: supports[index],
        lane_receptor_status: supports[index].length ? 'supported' : (unknown[notes[index].lane] ?? []).some(r => r.start_seconds <= range[1] && r.end_seconds >= range[0]) ? 'unknown' : 'unmeasured',
        ranking_offset_seconds: offset, alternative_rows: (event.delta ?? 1) === 1 ? sourceRows.get(event).length : 1, aggregate_row_capacity: event.delta ?? 1});
    }
  }
  return [result, Object.fromEntries(Object.entries(rejected).map(([i, r]) => [i, [...r].sort()]))];
}
