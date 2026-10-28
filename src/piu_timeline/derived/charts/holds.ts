import {contracts} from '../contracts.ts';
import {measures} from './transcription.ts';
import type {Document} from './ucs.ts';
import type {Interval, RecordData} from '../types.ts';
const P = contracts.hold_simplification;

export function continuousState(runs: RecordData[], lane: number, bridge: number[], origin: number): RecordData | null {
  for (let i = 0; i < runs.length; i++) {
    const run = runs[i];
    if (run.lane !== lane || run.lit !== true || (run.frames ?? 0) < 2) continue;
    const start = run.start_seconds, end = run.end_seconds;
    if ([start, end].some(t => typeof t !== 'number' || !Number.isFinite(t)) || !(start < end) || start > bridge[0] + origin || end < bridge[1] + origin) continue;
    return {channel: 'receptor_runs', run: i, playback_range: [start, end], source_pts_range: [run.first_source_pts_seconds ?? null, run.last_source_pts_seconds ?? null]};
  }
  return null;
}

export function simplify(doc: Document, observations: RecordData[], endpoints: Record<string, Interval>, notes: RecordData[], origin: number, runs: RecordData[] = []): [RecordData[], Record<string, Interval>, RecordData] {
  const spans = measures(doc), eligible = new Set(observations.filter(o => o.kind === 'hold').map(o => o.note)), blockers = new Map();
  notes.forEach((n, i) => {
    if (eligible.has(i) || n.note_type === 'hold_component' && n.reason === 'long_note_body_or_tail') return;
    const target = n.target_seconds, error = n.prediction_uncertainty_seconds ?? .02;
    const bounded = [target, error].every(v => typeof v === 'number' && Number.isFinite(v)) && 0 <= error && error <= .08;
    if (!blockers.has(n.lane)) blockers.set(n.lane, []);
    blockers.get(n.lane).push(bounded ? [target - origin - error, target - origin + error] : null);
  });
  const result = [], edges = {...endpoints}, merges = [];
  const holds = observations.filter(o => o.kind === 'hold').sort((a, b) => a.lane - b.lane ||
    edges[`${a.note},head`][0] + edges[`${a.note},head`][1] - edges[`${b.note},head`][0] - edges[`${b.note},head`][1]);
  for (const current of holds) {
    const item = {...current}, ni = item.note, head = edges[`${ni},head`], tail = edges[`${ni},tail`], previous = result.at(-1);
    if (previous && previous.lane === item.lane) {
      const pi = previous.note, old = edges[`${pi},tail`], lower = head[0] - old[1], upper = head[1] - old[0];
      const bridge = [Math.min(old[0], head[0]), Math.max(old[1], head[1])];
      const tempos = spans.filter(s => s.end.number() >= bridge[0] && s.start.number() <= bridge[1]).map(s => s.beat_duration.number());
      const tempo = tempos.length ? Math.min(...tempos) : 0;
      let limit = Math.min(P.maximum_gap_seconds, tempo * P.maximum_gap_beats);
      const state = continuousState(runs, item.lane, bridge, origin);
      if (state) limit = Math.max(limit, Math.min(P.held_state_maximum_gap_seconds, tempo * P.held_state_maximum_gap_beats));
      const blocked = (blockers.get(item.lane) ?? []).some(b => b === null || b[0] <= bridge[1] && b[1] >= bridge[0]);
      if (limit > 0 && -limit <= lower && lower <= upper && upper <= limit && tail[0] > old[1] && head[0] > edges[`${pi},head`][1] && !blocked) {
        if (!previous.source_hold_intervals) { previous.source_hold_intervals = [{...previous}]; previous.bridged_gaps = []; }
        previous.source_hold_intervals.push({...item});
        previous.bridged_gaps.push({song_range: bridge, gap_range_seconds: [lower, upper], maximum_gap_seconds: limit,
          basis: state ? 'continuous_held_state' : 'bounded_chart_geometry', held_state_evidence: state});
        previous.observed_end_range = item.observed_end_range; edges[`${pi},tail`] = tail;
        delete edges[`${ni},head`]; delete edges[`${ni},tail`]; continue;
      }
    }
    result.push(item);
  }
  for (const item of result) if (item.source_hold_intervals) merges.push({note: item.note, lane: item.lane, source_hold_intervals: item.source_hold_intervals, bridged_gaps: item.bridged_gaps});
  result.push(...observations.filter(o => o.kind !== 'hold').map(o => ({...o})));
  return [result, edges, {policy: P, merges}];
}
