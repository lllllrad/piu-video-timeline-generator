/** Union positive chart facts from unreviewed sources, preserving disagreements. */
import {grid, lanes, type Document} from './ucs.ts';
import {q} from './rational.ts';
import {transcribe,measures} from './transcription.ts';
import type {RecordData, Interval} from '../types.ts';

export interface Contribution {id:string;document:Document}
export function merge(template:Document, sources:Contribution[]): [Document, RecordData] {
  if (!sources.length || new Set(sources.map(s => s.id)).size !== sources.length) throw new Error('Draft sources must have unique identities');
  const notes = new Map<string,RecordData>(), weights = new Map<string,RecordData[]>(), conflicts = [];
  for (const source of sources) {
    if (lanes(source.document) !== lanes(template)) throw new Error('Draft modes conflict');
    const rows = grid(source.document), open = new Map<number,number>();
    for (const [si,ri,t] of rows) {
      const section = source.document.sections[si], cells = section.rows[ri], time = t.toString();
      const count = section.combo_counts?.[ri];
      // Legacy unannotated holds cannot assert a known tick on every body row.
      if (/[MHW]/.test(cells) && Object.fromEntries(source.document.header).Combo === '1' && count !== null) {
        if (!weights.has(time)) weights.set(time, []);
        weights.get(time).push({source:source.id,count:count ?? 1});
      }
      [...cells].forEach((cell,lane) => {
        if (cell === 'M') {
          if (open.has(lane)) throw new Error('Nested hold in draft contribution');
          open.set(lane,t.number());
        } else if (cell === 'W') {
          if (!open.has(lane)) throw new Error('Headless hold in draft contribution');
          add(lane,'hold',open.get(lane),t.number(),source.id);open.delete(lane);
        } else if (cell === 'H' && !open.has(lane)) throw new Error('Headless hold in draft contribution');
        else if (cell === 'X') add(lane,'tap',t.number(),t.number(),source.id);
        else if (cell === '.' && open.has(lane)) throw new Error('Broken hold in draft contribution');
      });
    }
    if (open.size) throw new Error('Unterminated hold in draft contribution');
  }
  function add(lane:number,kind:string,start:number,end:number,source:string) {
    const key = `${lane},${kind},${start.toFixed(9)},${end.toFixed(9)}`;
    if (!notes.has(key)) notes.set(key,{key,lane,kind,start,end,sources:[]});
    notes.get(key).sources.push(source);
  }
  const facts = [...notes.values()], rejected = new Set<string>();
  facts.forEach((a,i) => facts.slice(i+1).forEach(b => {
    if (a.lane === b.lane && a.start <= b.end + 1e-8 && b.start <= a.end + 1e-8) {
      rejected.add(a.key);rejected.add(b.key);conflicts.push({reason:'Conflicting chart geometry',facts:[a,b]});
    }
  }));
  const endpoints:Record<string,Interval> = {};
  const bounded = (t:number):Interval => [t-1e-8,t+1e-8];
  for (const f of facts) if (!rejected.has(f.key)) {
    endpoints[`${f.key},start`] = bounded(f.start);
    if (f.kind === 'hold') endpoints[`${f.key},end`] = bounded(f.end);
  }
  // Numeric tick rows are independent timing facts; unknown body rows add no grid constraint.
  for (const time of weights.keys()) endpoints[`tick,${time}`] = bounded(q(time).number());
  const skeleton = structuredClone(template), spans = measures(skeleton);
  const extent = sources.map(s => measures(s.document).at(-1).end).reduce((a,b) => a.cmp(b)>0?a:b);
  const end = spans.at(-1).end;
  if (extent.cmp(end)>0) {
    const tempos = new Set(spans.map(s => s.beat_duration.toString()));
    if (tempos.size !== 1) throw new Error('Cannot extend variable-tempo merge timing');
    const last = skeleton.sections.at(-1), settings = Object.fromEntries(skeleton.sections.flatMap(s => s.directives));
    const extra = extent.sub(end).div(spans.at(-1).beat_duration).mul(q(settings.Split)).integer();
    if (extra > 1536*900 || extra < 0) throw new Error('Merged timing extension exceeds supported extent');
    last.rows.push(...Array(extra).fill('.'.repeat(lanes(skeleton))));
  }
  const [doc,rows,accepted,failures,transcription] = transcribe(skeleton,endpoints);
  const placed = [];
  for (const f of facts) if (!rejected.has(f.key)) {
    const start = accepted[`${f.key},start`], end = f.kind === 'hold' ? accepted[`${f.key},end`] : start;
    if (start === undefined || end === undefined) { conflicts.push({reason:'Merged chart fact has no bounded row',fact:f});continue; }
    for (let row=start;row<=end;row++) {
      const [si,ri] = rows[row], chars = [...doc.sections[si].rows[ri]];
      chars[f.lane] = f.kind === 'tap' ? 'X' : row === start ? 'M' : row === end ? 'W' : 'H';doc.sections[si].rows[ri] = chars.join('');
    }
    placed.push({...f,start_row:start,end_row:end});
  }
  if (placed.some(p => p.kind === 'hold')) {
    doc.header = [...doc.header.filter(([k]) => k !== 'Combo'), ['Combo','1']];
    doc.sections.forEach(s => {s.combo_counts=s.rows.map(r => /[MHW]/.test(r) ? null : 1);});
    for (const [time,claims] of weights) {
      const row = accepted[`tick,${time}`];
      if (row === undefined) {conflicts.push({reason:'Merged tick has no bounded row',time,claims});continue;}
      const [si,ri] = rows[row];
      if (!/[MHW]/.test(doc.sections[si].rows[ri])) {conflicts.push({reason:'Tick has no unambiguous hold geometry',time,claims});continue;}
      const values = new Set(claims.map(c => c.count));
      if (values.size === 1) doc.sections[si].combo_counts[ri] = claims[0].count;
      else conflicts.push({reason:'Conflicting combo counts',time,claims});
    }
  }
  return [doc,{format:1,sources:sources.map(s => s.id),placements:placed,conflicts,failures,transcription}];
}

/** Keep current-recording source links valid after the union changes row indexes. */
export function remap(document:Document, proof:RecordData): RecordData {
  const rows = grid(document), positions = new Map(rows.map(([si,ri,t],row) => [t.number().toFixed(9),{si,ri,row}]));
  const placements = [], unresolved = [...proof.unresolved];
  for (const p of proof.placements) {
    const start = positions.get(p.song_seconds.toFixed(9)), end = positions.get(p.end_song_seconds.toFixed(9));
    if (!start || !end || document.sections[start.si].rows[start.ri][p.lane] !== (p.kind === 'hold' ? 'M' : 'X') ||
      p.kind === 'hold' && document.sections[end.si].rows[end.ri][p.lane] !== 'W') {
      unresolved.push({note:p.note,reason:'Source placement conflicts with merged draft'});continue;
    }
    placements.push({...p,start:start.row,end:end.row,section:start.si,row:start.ri,end_section:end.si,end_row:end.ri});
  }
  return {...proof,placements,unresolved,summary:{...proof.summary,placed_taps:placements.filter(p => p.kind === 'tap').length,
    placed_holds:placements.filter(p => p.kind === 'hold').length,unresolved_note_heads:unresolved.length}};
}

/** Summarize the final timing-row values; source observations remain separate. */
export function comboSummary(document:Document, annotation:RecordData): RecordData {
  const rows=grid(document),at=new Map(rows.map(([si,ri,t],row)=>[t.number().toFixed(9),{si,ri,row}]));
  const values=rows.flatMap(([si,ri,t],row)=>/[MHW]/.test(document.sections[si].rows[ri])?
    [{song_seconds:t.number(),row,si,ri,count:document.sections[si].combo_counts?.[ri]??null}]:[]);
  const placed=annotation.placed.flatMap(p=>{const point=at.get(p.song_seconds.toFixed(9));return point?[{...p,...point}]:[];});
  return {...annotation,placed,timing_rows:values,confirmed_hold_rows:values.filter(v=>v.count!==null).length,
    unknown_hold_rows:values.filter(v=>v.count===null).length};
}
