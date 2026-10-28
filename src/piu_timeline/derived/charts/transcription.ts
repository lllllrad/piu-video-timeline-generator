import {contracts, NATURAL_SPLITS} from '../contracts.ts';
import {lowerBound, upperBound} from '../math.ts';
import {q, lcm, type Rational} from './rational.ts';
import {grid, lanes, type Document, type Directive, type Section} from './ucs.ts';
import type {Interval, RecordData} from '../types.ts';
const F = contracts.transcription, EPS = 1e-8;

interface Span {source_section: number; measure: number; phase: Rational; beats: Rational; start: Rational; end: Rational; beat_duration: Rational; directives: Directive[]}
export function measures(doc: Document): Span[] {
  const settings: Record<string, string> = {}, result = [];
  let time = q(0), phase = q(0), meter = null, measure = 0;
  doc.sections.forEach((s, si) => {
    Object.assign(settings, Object.fromEntries(s.directives));
    const beat = Number(settings.Beat), split = Number(settings.Split);
    if (meter !== null && meter !== beat) { if (phase.n) measure++; phase = q(0); }
    meter = beat;
    time = time.add(q(Object.fromEntries(s.directives).Delay ?? '0').div(q(1000)));
    let remaining = q(s.rows.length).div(q(split));
    const duration = q(60).div(q(settings.BPM));
    let first = true;
    while (remaining.n) {
      const available = q(beat).sub(phase), length = remaining.cmp(available) < 0 ? remaining : available;
      result.push({source_section: si, measure, phase, beats: length, start: time, end: time.add(length.mul(duration)), beat_duration: duration, directives: first ? s.directives : []});
      first = false; time = time.add(length.mul(duration)); remaining = remaining.sub(length); phase = phase.add(length);
      if (phase.cmp(q(beat)) === 0) { phase = q(0); measure++; }
    }
  });
  return result;
}

export function choices(span: Span, split: number, lower: number, upper: number, following: number | null): number[][] {
  const step = span.beat_duration.div(q(split)).number(), start = span.start.number(), count = span.beats.mul(q(split)).integer();
  const lo = Math.max(0, Math.ceil((lower - start - EPS) / step)), hi = Math.min(count - 1, Math.floor((upper - start + EPS) / step));
  const rows = [];
  for (let i = lo; i <= hi; i++) rows.push([start + i * step, i]);
  if (following !== null && lower - EPS <= following && following <= upper + EPS) rows.push([following, count]);
  return rows;
}

export function choicesFromJSON(span, split, lower, upper, following): number[][] {
  const parsed = {...span};
  for (const key of ['phase', 'beats', 'start', 'end', 'beat_duration']) parsed[key] = q(span[key]);
  return choices(parsed, split, lower, upper, following);
}

export type TranscriptionResult = [Document, [number, number, Rational][], Record<string, number>, Record<string, string>, RecordData];
export function transcribe(doc: Document, endpoints: Record<string, Interval>): TranscriptionResult {
  const spans = measures(doc), starts = spans.map(s => s.start.number()), groups = spans.map(() => []);
  for (const [key, interval] of Object.entries(endpoints)) {
    const center = (interval[0] + interval[1]) / 2;
    groups[Math.max(0, Math.min(spans.length - 1, upperBound(starts, center) - 1))].push([key, interval]);
  }
  const sections: Section[] = [], fits: RecordData[] = [], assigned = {}, failures = {};
  let flat = 0;
  spans.forEach((span, index) => {
    const following = starts[index + 1] ?? null, factor = lcm(Number(span.phase.d), Number(span.beats.d));
    const splits = [...new Set(NATURAL_SPLITS.map(s => lcm(factor, s)).filter(s => s <= 1536))].sort((a, b) => a - b);
    const trials = [];
    let best = null;
    for (const split of splits) {
      const count = span.beats.mul(q(split)).integer(), step = span.beat_duration.div(q(split));
      if (following !== null && span.start.add(q(count - 1).mul(step)).number() >= following - EPS) continue;
      const matches = {}, rejected = {};
      for (const [key, [lower, upper]] of groups[index]) {
        const rows = choices(span, split, lower, upper, following);
        if (rows.length === 1 && Math.abs((lower + upper) / 2 - rows[0][0]) <= F.maximum_row_residual_seconds + EPS) matches[key] = rows[0];
        else rejected[key] = rows.length > 1 ? 'Ambiguous rows at selected measure Split' : 'No bounded row at selected measure Split';
      }
      const unique = Object.keys(matches).length;
      trials.push({split, unique_endpoints: unique});
      if (!best || unique > best.unique || unique === best.unique && split < best.split) best = {unique, split, matches, rejected};
    }
    if (!best) throw new Error('Official timing boundaries cannot form an increasing measure grid');
    const {split, matches, rejected} = best;
    const directives: Directive[] = [...span.directives.filter(([k]) => k !== 'Split'), ['Split', String(split)]];
    sections.push({directives, rows: Array(span.beats.mul(q(split)).integer()).fill('.'.repeat(lanes(doc)))});
    for (const [key, [time, row]] of Object.entries<number[]>(matches)) assigned[key] = [time, flat + row, index];
    for (const [key, reason] of Object.entries(rejected)) failures[key] = `${reason}=${split}`;
    fits.push({measure: span.measure, source_section: span.source_section, start_seconds: span.start.number(), end_seconds: span.end.number(),
      beat_offset: span.phase.toString(), split, row_duration_seconds: span.beat_duration.div(q(split)).number(),
      status: !groups[index].length ? 'empty' : Object.keys(rejected).length ? Object.keys(matches).length ? 'partial' : 'failed' : 'restored',
      endpoints: groups[index].length, unique_endpoints: Object.keys(matches).length, tested_splits: trials});
    flat += sections.at(-1).rows.length;
  });
  const result = {header: doc.header, sections}, rows = grid(result), times = rows.map(r => r[2].number());
  if (times.slice(1).some((t, i) => t <= times[i])) throw new Error('Overlapping UCS timing sections need manual placement');
  const accepted = {};
  for (const [key, [time, row, index]] of Object.entries<number[]>(assigned)) {
    const [lower, upper] = endpoints[key], lo = lowerBound(times, lower - EPS), hi = upperBound(times, upper + EPS);
    if (hi - lo !== 1 || lo !== row || Math.abs((lower + upper) / 2 - time) > F.maximum_row_residual_seconds + EPS) {
      failures[key] = 'Chart interval is ambiguous or outside tolerance across measure grids';
      fits[index].post_grid_unresolved_endpoints = (fits[index].post_grid_unresolved_endpoints ?? 0) + 1;
    } else accepted[key] = row;
  }
  fits.forEach((fit, i) => {
    const count = Object.keys(accepted).filter(k => assigned[k][2] === i).length;
    fit.unique_endpoints = count;
    fit.status = !fit.endpoints ? 'empty' : count === fit.endpoints ? 'restored' : count ? 'partial' : 'failed';
  });
  return [result, rows, accepted, failures, {format: F, measures: fits}];
}
