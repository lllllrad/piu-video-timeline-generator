/** Build an editable UCS draft from chart observations, independently of acquisition. */
import {q} from './rational.ts';
import {expanded, grid, type Document} from './ucs.ts';
import {transcriptionAlignment} from './phase.ts';
import {simplify} from './holds.ts';
import {transcribe} from './transcription.ts';
import type {Interval, RecordData} from '../types.ts';

export function canonicalChart(data: RecordData): string | null {
  const chart = data.chart ?? '';
  if (/^[SD]\d{1,2}$/.test(chart)) return chart;
  const id = data.chart_identity ?? {}, frames = id.source_frames ?? [];
  const pts = new Set(frames.filter(f => f.file && typeof f.source_pts_seconds === 'number' && Number.isFinite(f.source_pts_seconds)).map(f => f.source_pts_seconds));
  if (id.status === 'recognized' && id.method === 'matching_title_summary_badge' && id.display_chart === chart && pts.size >= 2 &&
    /^VERY HARD \d{1,2}$/.test(chart) && id.chart === 'S' + chart.slice('VERY HARD '.length)) return id.chart;
  return null;
}

export function draft(template: Document, view: RecordData, alignment: RecordData, extend = false): [Document, RecordData] {
  const chart = canonicalChart(view);
  if (!chart) throw new Error('A recognized Single/Double chart and level are required');
  const lanes = chart.startsWith('S') ? 5 : 10;
  if (view.layout.lanes.length !== lanes) throw new Error('Recognized chart mode conflicts with analyzed lane geometry');
  const [calibration, phaseProof] = transcriptionAlignment(template, view, alignment);
  let doc = expanded(template, lanes), rows = grid(doc), extension = null;
  if (extend) {
    const ends = view.notes.filter(n => n.status === 'estimated' && Number.isFinite(n.target_seconds) && (n.prediction_uncertainty_seconds ?? .02) <= .08)
      .map(n => n.target_seconds - calibration.song_start_seconds);
    ends.push(...(view.hold_analysis?.holds ?? []).filter(h => h.end_range && !h.end_censored).map(h => (h.end_range[0] + h.end_range[1]) / 2 - calibration.song_start_seconds));
    const latest = Math.min((ends.length ? Math.max(...ends) : 0) + .05, view.end_seconds - calibration.song_start_seconds + .1), settings: Record<string, string> = {};
    doc.sections.forEach(s => Object.assign(settings, Object.fromEntries(s.directives)));
    const step = q(60).div(q(settings.BPM).mul(q(settings.Split))), originalEnd = rows.at(-1)[2], fraction = q(String(latest)).sub(originalEnd).div(step);
    const additional = Math.max(0, fraction.ceil());
    if (additional) {
      if (q(additional).mul(step).cmp(q(900)) > 0) throw new Error('Timing extension exceeds supported song duration');
      doc.sections.at(-1).rows.push(...Array(additional).fill('.'.repeat(lanes))); rows = grid(doc);
      extension = {basis: 'constant_tempo_catalogue_and_template', additional_rows: additional, original_last_row_seconds: originalEnd.number(), extended_last_row_seconds: rows.at(-1)[2].number(), review_required: true};
    }
  }
  if (rows.slice(1).some((r, i) => r[2].cmp(rows[i][2]) <= 0)) throw new Error('Overlapping UCS timing sections need manual placement');
  const origin = calibration.song_start_seconds, alignmentError = calibration.uncertainty_seconds;
  if (!Number.isFinite(origin) || !Number.isFinite(alignmentError) || alignmentError < 0 || alignmentError > .1) throw new Error('Song alignment must be finite');
  const holds = new Map<number, RecordData>((view.hold_analysis?.holds ?? []).map(h => [h.display_note, h])), pending = [], observed = [], endpoints: Record<string, Interval> = {};
  const interval = (target, uncertainty): Interval => {
    if (!Number.isFinite(target) || !Number.isFinite(uncertainty) || uncertainty < 0 || uncertainty > .08) throw new Error('Unbounded visible-note timing');
    const error = uncertainty + alignmentError;
    return [target - origin - error, target - origin + error];
  };
  view.notes.forEach((n, ni) => {
    if (n.status !== 'estimated') return;
    try {
      const lane = n.lane;
      if (!Number.isInteger(lane) || lane < 0 || lane >= lanes) throw new Error('Invalid observed lane');
      const hold = holds.get(ni), kind = n.type_status;
      if (kind === 'conflict') throw new Error('Contradictory tap and hold observations');
      if (!hold && kind !== 'tap') throw new Error(kind === 'hold' ? 'Observed hold cap has no resolved hold geometry' : 'Note type is unverified');
      const uncertainty = n.prediction_uncertainty_seconds ?? .02, head = interval(n.target_seconds, uncertainty);
      let tail = null;
      if (hold) {
        if (hold.start_censored || hold.end_censored || !hold.end_range) throw new Error('Hold endpoint is censored');
        const end = hold.end_range; tail = interval((end[0] + end[1]) / 2, (end[1] - end[0]) / 2);
      }
      endpoints[`${ni},head`] = head;
      if (tail) endpoints[`${ni},tail`] = tail;
      observed.push({note: ni, lane, kind: hold ? 'hold' : 'tap', observed_target_range: [n.target_seconds - uncertainty, n.target_seconds + uncertainty], ...(hold ? {observed_end_range: hold.end_range} : {})});
    } catch (error) {
      if (!['Invalid observed lane', 'Contradictory tap and hold observations', 'Observed hold cap has no resolved hold geometry',
        'Note type is unverified', 'Unbounded visible-note timing', 'Hold endpoint is censored'].includes(error.message)) throw error;
      pending.push({note: ni, reason: error.message});
    }
  });
  const [observations, edges, simplifications] = simplify(doc, observed, endpoints, view.notes, origin, view.hold_analysis?.receptor_runs ?? []);
  const [output, newGrid, accepted, failures, proof] = transcribe(doc, edges);
  doc = output; rows = newGrid;
  const proposals = [];
  for (const o of observations) {
    const ni = o.note, keys = o.kind === 'hold' ? ['head', 'tail'] : ['head'];
    const rejected = Object.fromEntries(keys.filter(k => !Object.hasOwn(accepted, `${ni},${k}`)).map(k => [k, failures[`${ni},${k}`]]));
    if (Object.keys(rejected).length) { pending.push({note: ni, reason: 'Measure timing reconstruction failed', endpoints: rejected}); continue; }
    const start = accepted[`${ni},head`], end = accepted[`${ni},tail`] ?? start;
    if (o.kind === 'hold' && end <= start) { pending.push({note: ni, reason: 'Hold endpoints share or reverse a timing row'}); continue; }
    const target = (o.observed_target_range[0] + o.observed_target_range[1]) / 2 - origin;
    proposals.push({...o, start, end, residual_seconds: rows[start][2].number() - target});
  }
  const occupied = new Map<string, number[]>();
  proposals.forEach((p, i) => { for (let row = p.start; row <= p.end; row++) {
    const key = `${row},${p.lane}`; if (!occupied.has(key)) occupied.set(key, []); occupied.get(key).push(i);
  } });
  const conflicts = new Set([...occupied.values()].filter(a => a.length > 1).flat()), placements = [];
  proposals.forEach((p, i) => {
    if (conflicts.has(i)) { pending.push({note: p.note, reason: 'Conflicting observed notes occupy the same lane and timing row'}); return; }
    for (let row = p.start; row <= p.end; row++) {
      const [si, ri] = rows[row], chars = [...doc.sections[si].rows[ri]];
      chars[p.lane] = p.kind === 'tap' ? 'X' : row === p.start ? 'M' : row === p.end ? 'W' : 'H';
      doc.sections[si].rows[ri] = chars.join('');
    }
    const [si, ri, time] = rows[p.start], [ei, er, endTime] = rows[p.end];
    placements.push({...p, section: si, row: ri, song_seconds: time.number(), end_section: ei, end_row: er, end_song_seconds: endTime.number()});
  });
  if (!placements.length) throw new Error('No bounded notes can be placed on the official timing grid');
  const excluded = {};
  for (const n of view.notes) if (n.status !== 'estimated') { const reason = String(n.reason ?? null); excluded[reason] = (excluded[reason] ?? 0) + 1; }
  return [doc, {placements, unresolved: pending, timing_extension: extension, transcription: proof, transcription_alignment: phaseProof, hold_simplifications: simplifications,
    summary: {placed_taps: placements.filter(p => p.kind === 'tap').length, placed_holds: placements.filter(p => p.kind === 'hold').length, unresolved_note_heads: pending.length, excluded_observations: excluded}}];
}
