import {associationWindow, candidates, EARLY, intersectWindow, LATE} from './candidates.ts';
import {assignments, bracket, notePolicy} from './evidence.ts';
import {entries} from './math.ts';
import type {RecordData} from './types.ts';

export function counterFrameRanges(frames: RecordData[]): RecordData[] {
  const events = [];
  let previous = null;
  for (const f of frames) {
    const value = f.combo;
    if (value == null || (f.combo_confidence ?? 0) < .8) continue;
    const current = [f.playback_seconds, value, f.source_pts_seconds];
    if (previous) {
      const delta = value - previous[1], span = current[0] - previous[0];
      if (0 < delta && delta <= 10 && 0 < span && span <= 1) events.push({delta, lower_seconds: previous[0], upper_seconds: current[0], source_pts_seconds: [previous[2], current[2]],
        before: previous[1], after: value, reason: 'unconfirmed_positive_counter_frame_change'});
    }
    previous = current;
  }
  return events;
}
export function timingRanges(data: RecordData): RecordData {
  const withPolicy = (record, note) => {
    const policy = notePolicy(data, note);
    if (policy) { record.chart_policy = policy; if (policy.suppress_timing) Object.assign(record, {status: 'policy_excluded', reason: 'chart_region_processing_exception', input_ranges: []}); }
    return record;
  };
  const matches = new Map(assignments(data).map(m => [m.note, m])), misses = new Set((data.miss_candidates ?? []).map(c => c.note)), events = [];
  for (const [source, key] of [['combo', 'combo_events'], ['judgment', 'judgment_events'], ['counter_frames', 'counter_frame_events']]) {
    (data[key] ?? []).forEach((e, index) => {
      if (['combo', 'counter_frames'].includes(source) && (e.delta ?? 0) <= 0 || source === 'combo' && e.judged_row_count === null || source === 'judgment' && e.label === 'MISS') return;
      const lo = e.lower_seconds, hi = e.upper_seconds;
      if (Number.isFinite(lo) && Number.isFinite(hi) && lo <= hi) events.push({source, event: index, delta: (Object.hasOwn(e, 'judged_row_count') ? e.judged_row_count : (e.delta ?? 1)) || 0, lower_seconds: lo, upper_seconds: hi, reason: e.reason ?? null,
        ...(Object.hasOwn(e, 'before') && Object.hasOwn(e, 'after') ? {before: e.before, after: e.after} : {}), ...(e.source_pts_seconds ? {source_pts_seconds: e.source_pts_seconds} : {})});
    });
  }
  const holds = new Map<number, RecordData>((data.hold_analysis?.holds ?? []).map(h => [h.id, h])), trusted = [...matches.values()].filter(m => !m.processing_conflict);
  const [constrained, rejected] = candidates({...data, matches: trusted}, events), ordered = [...trusted].sort((a, b) => a.target_seconds - b.target_seconds), result = {};
  (data.notes ?? []).forEach((note, index) => {
    if (note.status !== 'estimated') return;
    const target = note.target_seconds, error = note.prediction_uncertainty_seconds, window = associationWindow(note, (data.display_delay_correction_ms ?? 0) / 1000);
    const record: RecordData = {association_window: window, target_range: [target - error, target + error], input_ranges: [], rejected_candidates: rejected[index] ?? []};
    if (note.note_type === 'hold') {
      const hold = holds.get(note.hold_id), ranges = hold.input.segments.map(s => [s.lower_seconds, s.upper_seconds]);
      result[index] = withPolicy({...record, status: ranges.length ? 'hold_state' : 'hold_unresolved', input_ranges: ranges, target_range: hold.start_range, end_range: hold.end_range,
        reason: 'sustained_state_not_repeated_presses', input_requirement: 'held_state', requires_head_press: false, input_kind: 'sustained_recognition', press_range: null, release_range: null}, note);
      return;
    }
    const match = matches.get(index);
    if (match && match.judgment_label !== 'MISS') {
      const [lo, hi] = bracket(match);
      if (lo != null && hi != null) {
        const clipped = intersectWindow([lo, hi], window);
        Object.assign(record, {status: clipped ? 'matched' : 'unknown', input_ranges: clipped ? [clipped] : [], observed_input_range: [lo, hi], reason: clipped ? 'matched_display_refresh' : 'outside_association_window'});
        if (match.processing_conflict) Object.assign(record, {status: 'conflicted', input_ranges: [], reason: 'assigned_refresh_conflicts_with_note_processing', processing_passage: match.processing_passage_after_refresh ?? null});
      }
    }
    if (!Object.hasOwn(record, 'status')) {
      if (misses.has(index) || match?.judgment_label === 'MISS') Object.assign(record, {status: 'possible_miss', reason: 'possible_miss_has_no_press_timestamp'});
      else {
        const alternatives = constrained[index] ?? [], intervals = [];
        for (const [lo, hi] of alternatives.map(e => e.candidate_range).sort((a, b) => a[0] - b[0] || a[1] - b[1])) {
          if (intervals.length && lo <= intervals.at(-1)[1]) intervals.at(-1)[1] = Math.max(intervals.at(-1)[1], hi); else intervals.push([lo, hi]);
        }
        Object.assign(record, {status: alternatives.length ? 'possible' : 'unknown', input_ranges: intervals,
          reason: alternatives.length ? 'ambiguous_display_association' : record.rejected_candidates.length ? 'nearby_refresh_rejected_by_constraints' : 'no_nearby_positive_refresh', alternatives});
        if (!intervals.length && !record.rejected_candidates.length) {
          const before = [...ordered].reverse().find(m => m.target_seconds < target - .025), after = ordered.find(m => m.target_seconds > target + .025);
          if (before && after && after.target_seconds - before.target_seconds <= 3) {
            const lo = bracket(before)[0], hi = bracket(after)[1], clipped = lo != null && hi != null ? intersectWindow([lo, hi], window) : null;
            if (clipped) Object.assign(record, {status: 'bounded', reason: 'between_neighboring_processed_rows', input_ranges: [clipped], neighbor_observation_range: [lo, hi], anchors: [before.note, after.note],
              condition: 'Bounds assume this note was pressed in chart-row order; they do not establish a press.'});
          }
        }
      }
    }
    if (record.status === 'unknown' && record.reason !== 'outside_association_window') {
      if ((data.combo_events ?? []).some(e => (e.delta ?? 0) <= 0 && e.lower_seconds <= target && target <= e.upper_seconds)) record.reason = 'counter_reset_without_resolved_press';
      else if ((data.unsupported_intervals ?? []).some(i => i.start_seconds - .1 <= target && target <= i.end_seconds + .1)) record.reason = 'hold_or_dense_stack_without_resolved_refresh';
      else if (events.length && target < Math.min(...events.map(e => e.lower_seconds))) record.reason = 'before_first_detected_positive_refresh';
      else if (events.length && target > Math.max(...events.map(e => e.upper_seconds))) record.reason = 'after_last_detected_positive_refresh';
    }
    result[index] = withPolicy(record, note);
  });
  const counts = {}, eligible = {};
  for (const [, r] of entries<RecordData>(result)) {
    counts[r.status] = (counts[r.status] ?? 0) + 1;
    if (r.status !== 'policy_excluded' && !(r.chart_policy?.check_exceptions ?? []).includes('timing_evidence')) eligible[r.status] = (eligible[r.status] ?? 0) + 1;
  }
  return {notes: result, counts, eligible_counts: eligible, association_limits_seconds: {early: EARLY, late: LATE},
    note: 'Connected ranges intersect original observations with hard timing limits. Possible ranges remain unconfirmed; original observations and source PTS are preserved.'};
}
