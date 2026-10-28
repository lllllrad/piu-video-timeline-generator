import {grid, lanes, type Document} from './ucs.ts';

export function validate(doc: Document, assertions: unknown): void {
  if (!Array.isArray(assertions)) throw new Error('Chart row assertions must be a list');
  const seen = new Set(), rows = assertions.length ? grid(doc) : [];
  for (const fact of assertions) {
    if (!fact || typeof fact !== 'object' || Array.isArray(fact) || Object.keys(fact).sort().join(',') !== 'cells,end_seconds,id,reason,start_seconds' ||
      typeof fact.id !== 'string' || !fact.id || seen.has(fact.id) || typeof fact.reason !== 'string' || !fact.reason.trim()) throw new Error('Invalid reviewed chart row assertion');
    seen.add(fact.id);
    const lo = fact.start_seconds, hi = fact.end_seconds, cells = fact.cells;
    if ([lo, hi].some(t => typeof t !== 'number' || !Number.isFinite(t)) || !(0 <= lo && lo < hi) || !cells || typeof cells !== 'object' || Array.isArray(cells) || !Object.keys(cells).length) {
      throw new Error('Invalid reviewed chart assertion interval or cells');
    }
    if (Object.entries(cells).some(([lane, kind]) => !/^\d+$/.test(lane) || Number(lane) >= lanes(doc) || !['.', 'X', 'M', 'H', 'W'].includes(kind as string))) {
      throw new Error('Invalid reviewed chart assertion lane or note kind');
    }
    if (!rows.some(([si, ri, t]) => lo <= t.number() && t.number() < hi && Object.entries(cells).every(([lane, kind]) => doc.sections[si].rows[ri][Number(lane)] === kind))) {
      throw new Error(`Chart row assertion ${fact.id} failed: ${fact.reason}`);
    }
  }
}
