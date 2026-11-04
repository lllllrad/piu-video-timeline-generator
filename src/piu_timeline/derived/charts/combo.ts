/** Timing-row combo weights are independent of lane ownership and physical presses. */
import {grid, type Document} from './ucs.ts';
import {contracts} from '../contracts.ts';
import type {RecordData} from '../types.ts';

export const RULE = {
  schema:1, default_increment:1, unit:'simultaneous_timing_row',
  simultaneous_taps:'confirmed', simultaneous_holds:'assumed', mixed_tap_hold:'assumed',
};
export function annotate(document: Document, proof: RecordData, source: RecordData): [Document, RecordData] {
  const doc = structuredClone(document), rows = grid(doc), origin = proof.transcription_alignment.song_start_seconds;
  const delay = (source.display_delay_correction_ms ?? 0) / 1000;
  const error = contracts.transcription.maximum_row_residual_seconds;
  const holds = proof.placements.filter(p => p.kind === 'hold'), placed = [], unresolved = [];
  if (!holds.length) return [doc, {format:1,rule:RULE,placed,unresolved}];
  doc.header = [...doc.header.filter(([k]) => k !== 'Combo'), ['Combo', '1']];
  for (const s of doc.sections) s.combo_counts = s.rows.map(r => /[MHW]/.test(r) ? null : 1);
  const events = [
    ...(source.combo_events ?? []).map((e, index) => ({...e, channel:'combo_events', index})),
    ...(source.judgment_events ?? []).map((e, index) => ({...e, channel:'judgment_events', index})).filter(e => ['PERFECT','GREAT','GOOD','BAD'].includes(e.label)),
  ];
  const claims = new Map<number, RecordData[]>();
  for (const e of events) {
    const lower = e.lower_seconds - delay, upper = e.upper_seconds - delay;
    if (![lower,upper].every(Number.isFinite) || lower > upper) continue;
    // Ignore counter resets and words outside any observed hold; retain hold-related failures.
    if (e.detection_status === 'excluded' || e.channel === 'combo_events' && !(e.delta > 0)) continue;
    const active = holds.filter(h => h.song_seconds + origin <= upper && lower <= h.end_song_seconds + origin);
    if (!active.length) continue;
    const reject = reason => unresolved.push({channel:e.channel,index:e.index,observation_range:[e.lower_seconds,e.upper_seconds],raw_delta:e.delta??null,reason});
    if (upper-lower > .1) {reject('Refresh bracket is too broad to identify one timing row');continue;}
    const effects = (source.chart_policy?.gimmick_candidates ?? []).filter(g => g.kind === 'suspected_multi_increment' && g.review_status !== 'rejected' &&
      g.playback_start_seconds <= e.lower_seconds && e.upper_seconds < g.playback_end_seconds);
    const increments = [...new Set(effects.map(g => g.combo_increment))];
    if (increments.length > 1) { reject('Conflicting configured combo increments'); continue; }
    const count = increments[0] ?? RULE.default_increment;
    if (typeof count !== 'number' || !Number.isSafeInteger(count) || count < 1 || count > 10) { reject('Invalid configured combo increment'); continue; }
    if (e.channel === 'combo_events' && e.delta !== count) { reject('Counter increment does not identify a single timing row'); continue; }
    const candidates = rows.flatMap(([si,ri,t],row) => /[MHW]/.test(doc.sections[si].rows[ri]) &&
      lower-origin-1e-8 <= t.number() && t.number() <= upper-origin+1e-8 &&
      Math.abs(t.number()-((lower+upper)/2-origin)) <= error+1e-8 ? [{row,si,ri}] : []);
    if (candidates.length !== 1) { reject('Combo refresh has no unique bounded timing row on the chart grid'); continue; }
    const c=candidates[0],item={...c,song_seconds:rows[c.row][2].number(),count,channel:e.channel,index:e.index,raw_delta:e.delta??null,label:e.label??null,
      observation_range:[e.lower_seconds,e.upper_seconds],display_delay_seconds:delay,rule:RULE,gimmick_candidates:effects.map(g=>g.id)};
    if (!claims.has(c.row)) claims.set(c.row, []);
    claims.get(c.row).push(item);
  }
  for (const items of claims.values()) {
    // Conflicting values or distinct same-channel transitions cannot be collapsed silently.
    const distinct = items.some((a,i)=>items.slice(i+1).some(b=>a.channel===b.channel &&
      (a.observation_range[1]<b.observation_range[0] || b.observation_range[1]<a.observation_range[0])));
    if (distinct || new Set(items.map(i=>i.count)).size !== 1) {unresolved.push({reason:'Conflicting refreshes at one timing row',updates:items});continue;}
    const item=items[0];doc.sections[item.si].combo_counts[item.ri]=item.count;
    placed.push({...item,observations:items});
  }
  return [doc,{format:1,rule:RULE,semantics:'Potential combo increment per timing row on PERFECT/GREAT; unknown rows remain ?',placed,unresolved,
    unknown_hold_rows:doc.sections.reduce((n,s)=>n+s.combo_counts.filter(c=>c===null).length,0)}];
}
