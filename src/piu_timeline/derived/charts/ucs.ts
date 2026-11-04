import {q, lcm, type Rational} from './rational.ts';
export type Directive = [string, string];
export interface Section {directives: Directive[]; rows: string[]; combo_counts?: (number | null)[]}
export interface Document {header: Directive[]; sections: Section[]}
export const lanes = (doc: Document): number => Object.fromEntries(doc.header).Mode === 'Single' ? 5 : 10;

export function parse(text: string): Document {
  const header: Directive[] = [], sections: Section[] = [];
  let directives: Directive[] = [], rows: string[] = [], counts: (number | null)[] = [];
  const section = (): Section => ({directives, rows, ...(Object.fromEntries(header).Combo === '1' ? {combo_counts: counts} : {})});
  const settings: Record<string, string> = {};
  for (const raw of text.replace(/^\uFEFF/, '').split(/\r\n|\r|\n/)) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith(':')) {
      const eq = line.indexOf('=');
      if (eq === -1) throw new Error('Malformed UCS directive');
      const key = line.slice(1, eq), value = line.slice(eq + 1);
      if (['Format', 'Mode', 'Combo'].includes(key)) {
        if (rows.length || sections.length || directives.length || header.some(([k]) => k === key)) throw new Error('UCS header must precede timing sections');
        if (key === 'Combo' && value !== '1') throw new Error('Unsupported UCS Combo extension');
        header.push([key, value]); continue;
      }
      if (!['BPM', 'Delay', 'Beat', 'Split'].includes(key)) throw new Error(`Unsupported UCS directive: ${key}`);
      if (rows.length) { sections.push(section()); directives = []; rows = []; counts = []; }
      if (directives.some(([k]) => k === key)) throw new Error(`Duplicate UCS directive: ${key}`);
      try {
        const number = q(value);
        if (key !== 'Delay' && number.n <= 0n || ['Beat', 'Split'].includes(key) && number.d !== 1n) throw new Error('Invalid UCS timing value');
      } catch { throw new Error(`Invalid UCS ${key}: ${value}`); }
      directives.push([key, value]); settings[key] = value;
    } else {
      if (!['BPM', 'Beat', 'Split'].every(k => Object.hasOwn(settings, k))) throw new Error('UCS rows require BPM, Beat and Split');
      const mode = Object.fromEntries(header).Mode, fields = line.split(/\s+/), cells = fields[0];
      if (fields.length > 2 || fields.length === 2 && (Object.fromEntries(header).Combo !== '1' || !/^(?:\d+|\?)$/.test(fields[1]))) throw new Error('Invalid UCS combo count');
      const count = fields[1] === '?' ? null : Number(fields[1] ?? '1');
      if (count !== null && !Number.isSafeInteger(count)) throw new Error('Invalid UCS combo count');
      if (!['Single', 'Double'].includes(mode) || cells.length !== (mode === 'Single' ? 5 : 10) || /[^.XMHW]/.test(cells)) throw new Error('Invalid UCS note row');
      rows.push(cells); counts.push(count);
    }
  }
  if (rows.length) sections.push(section());
  else if (directives.length) throw new Error('UCS section has no timing rows');
  if (Object.fromEntries(header).Format !== '1' || !sections.length) throw new Error('Expected a nonempty Format=1 UCS document');
  return {header, sections};
}

export function grid(doc: Document): [number, number, Rational][] {
  let time = q(0);
  const settings: Record<string, string> = {}, result = [];
  doc.sections.forEach((section, si) => {
    const directives = Object.fromEntries(section.directives);
    Object.assign(settings, directives);
    time = time.add(q(directives.Delay ?? '0').div(q(1000)));
    const step = q(60).div(q(settings.BPM).mul(q(settings.Split)));
    for (let ri = 0; ri < section.rows.length; ri++) { result.push([si, ri, time]); time = time.add(step); }
  });
  return result;
}

export function expanded(doc: Document, count: number, subdivisions = 1): Document {
  if (![5, 10].includes(count) || !Number.isInteger(subdivisions) || subdivisions < 1 || subdivisions > 192) throw new Error('Unsupported lane count or subdivision');
  const header = doc.header.map(([k, v]) => [k, k === 'Mode' ? count === 5 ? 'Single' : 'Double' : v] as Directive);
  let oldSplit = null;
  const sections = doc.sections.map(s => {
    oldSplit = Number(Object.fromEntries(s.directives).Split ?? oldSplit);
    const split = lcm(oldSplit, subdivisions);
    if (split > 1536) throw new Error('UCS subdivision expansion is too large');
    const directives = s.directives.map(([k, v]) => [k, k === 'Split' ? String(split) : v] as Directive);
    if (!directives.some(([k]) => k === 'Split')) directives.push(['Split', String(split)]);
    if (s.combo_counts?.some(c => c !== 1)) throw new Error('Cannot expand annotated combo timing as an empty template');
    if (s.rows.some(r => !/^\.+$/.test(r))) throw new Error('Expected an empty timing template');
    const rows = Array(s.rows.length * (split / oldSplit)).fill('.'.repeat(count));
    return {directives, rows, ...(Object.fromEntries(header).Combo === '1' ? {combo_counts: rows.map(() => 1)} : {})};
  });
  return {header, sections};
}
/** Remove the local extension for consumers that require standard UCS. */
export function standard(doc: Document): Document {
  return {header: doc.header.filter(([k]) => k !== 'Combo'), sections: doc.sections.map(s => ({directives: s.directives, rows: s.rows}))};
}
export function text(doc: Document): string {
  const extended = Object.fromEntries(doc.header).Combo === '1';
  const rows = (s: Section): string[] => {
    if (s.combo_counts != null && (!extended || s.combo_counts.length !== s.rows.length)) throw new Error('UCS combo counts require Combo=1 and one value per row');
    return s.rows.map((r, i) => {
      const count = s.combo_counts == null ? 1 : s.combo_counts[i];
      if (count !== null && (!Number.isSafeInteger(count) || count < 0)) throw new Error('Invalid UCS combo count');
      return r + (count === 1 ? '' : ` ${count === null ? '?' : count}`);
    });
  };
  return [...doc.header.map(([k, v]) => `:${k}=${v}`), ...doc.sections.flatMap(s => [...s.directives.map(([k, v]) => `:${k}=${v}`), ...rows(s)])].join('\n') + '\n';
}
export function constantTempo(doc: Document, bpm: unknown): boolean {
  if (typeof bpm !== 'string' || !/^\d+(?:\.\d+)?$/.test(bpm) || q(bpm).n <= 0n) return false;
  const bpms = doc.sections.flatMap(s => s.directives.filter(([k]) => k === 'BPM').map(([, v]) => q(v).toString()));
  return bpms.length > 0 && bpms.every(v => v === q(bpm).toString());
}
