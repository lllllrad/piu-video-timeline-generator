/** Ordered row-to-refresh alignment. Chords share a row and aggregate bracket. */
import type {RecordData} from './types.ts';

export function associate(notes: RecordData[], events: RecordData[], window = .045, delay = 0, constraints: Record<string, number[]> | null = null): RecordData[] {
  if (notes.some(n => n.status === 'estimated' && (typeof n.target_seconds !== 'number' || !Number.isFinite(n.target_seconds)))) throw new Error('Estimated rows require finite target times');
  const rows = [];
  notes.map((n, i) => [i, n] as const).sort((a, b) => (a[1].target_seconds ?? Infinity) - (b[1].target_seconds ?? Infinity)).forEach(([i, n]) => {
    if (n.status !== 'estimated') return;
    if (rows.length && Math.abs(n.target_seconds - rows.at(-1).seconds) < .025) rows.at(-1).notes.push(i);
    else rows.push({seconds: n.target_seconds, notes: [i]});
  });
  const selected = events.flatMap((e, i) => e.status === 'candidate' ? [[i, e] as const] : []), lengths = selected.map(([, e]) => e.delta ?? 1);
  const width = rows.length + 1, weights = selected.map(() => new Float64Array(rows.length)), links = [];
  selected.forEach(([index, e], i) => {
    const count = lengths[i], center = (e.lower_seconds + e.upper_seconds) / 2, span = e.upper_seconds - e.lower_seconds, radius = span / 2 + window;
    if (count < 1 || count > 10) return;
    for (let j = 0; j <= rows.length - count; j++) {
      const group = rows.slice(j, j + count), allowed = constraints?.[index];
      if (allowed && group.some(r => r.notes.some(k => !allowed.includes(k)))) continue;
      if (group.some(r => new Set(r.notes.map(k => notes[k].lane)).size !== r.notes.length)) continue;
      const distances = group.map(r => Math.abs(r.seconds + delay - center));
      if (Math.max(...distances) > radius || group.at(-1).seconds - group[0].seconds > span + .02) continue;
      weights[i][j] = count * (1 - .5 * (distances.reduce((a, b) => a + b, 0) / count / radius) ** 2); links.push([i, j, count]);
    }
  });
  const forward = new Float64Array((selected.length + 1) * width), backward = new Float64Array(forward.length);
  lengths.forEach((count, i) => {
    for (let end = 1; end <= rows.length; end++) {
      const paired = 0 < count && count <= end && weights[i][end - count] ? forward[i * width + end - count] + weights[i][end - count] : 0;
      forward[(i + 1) * width + end] = Math.max(forward[i * width + end], forward[(i + 1) * width + end - 1], paired);
    }
  });
  for (let i = selected.length - 1; i >= 0; i--) {
    const count = lengths[i];
    for (let j = rows.length - 1; j >= 0; j--) {
      const paired = weights[i][j] ? weights[i][j] + backward[(i + 1) * width + j + count] : 0;
      backward[i * width + j] = Math.max(backward[(i + 1) * width + j], backward[i * width + j + 1], paired);
    }
  }
  const path = [];
  let i = selected.length, j = rows.length;
  while (i && j) {
    const count = lengths[i - 1];
    if (0 < count && count <= j && weights[i - 1][j - count] && Math.abs(forward[i * width + j] - forward[(i - 1) * width + j - count] - weights[i - 1][j - count]) < 1e-9) {
      path.push([i - 1, j - count]); i--; j -= count;
    } else if (forward[(i - 1) * width + j] >= forward[i * width + j - 1]) i--; else j--;
  }
  const accepted = new Map(), optimum = forward.at(-1);
  for (const [i, j] of path) {
    const count = lengths[i];
    const alternatives = links.filter(([k, l, n]) => !(k === i && l === j) && (k === i || l < j + count && l + n > j))
      .map(([k, l, n]) => forward[k * width + l] + weights[k][l] + backward[(k + 1) * width + l + n]);
    if (!alternatives.length || optimum - Math.max(...alternatives) > .08) accepted.set(i, j);
  }
  const matches = [];
  selected.forEach(([index, e], i) => {
    if (!accepted.has(i)) { Object.assign(e, {status: 'excluded', reason: 'ambiguous_note_or_combo_association'}); return; }
    Object.assign(e, {status: 'matched', reason: null});
    for (const row of rows.slice(accepted.get(i), accepted.get(i) + lengths[i])) for (const ni of row.notes) {
      const target = notes[ni].target_seconds;
      matches.push({note: ni, combo_event: index, target_seconds: target, row_note_count: row.notes.length, aggregate_row_count: lengths[i],
        combo_lower_seconds: e.lower_seconds, combo_upper_seconds: e.upper_seconds, raw_offset_lower_ms: 1000 * (e.lower_seconds - target), raw_offset_upper_ms: 1000 * (e.upper_seconds - target)});
    }
  });
  return matches.sort((a, b) => a.target_seconds - b.target_seconds);
}

export function synchronizedRefreshes(data: RecordData, events: RecordData[]): number[][] {
  const links = [];
  events.forEach((e, ji) => {
    if (e.status !== 'candidate' || e.upper_seconds - e.lower_seconds > .05) return;
    (data.combo_events ?? []).forEach((c, ci) => {
      if (c.delta !== 1 || c.upper_seconds - c.lower_seconds > .1 + 1e-6 || c.status !== 'matched' && c.reason !== 'ambiguous_note_or_combo_association') return;
      const overlap = Math.min(e.upper_seconds, c.upper_seconds) - Math.max(e.lower_seconds, c.lower_seconds), distance = Math.abs(e.upper_seconds - c.upper_seconds);
      if (overlap >= -1e-6 && distance <= .025) links.push([distance, ji, ci]);
    });
  });
  const pairs = links.filter(([distance, ji, ci]) => {
    const others = links.filter(([, j, c]) => !(j === ji && c === ci) && (j === ji || c === ci)).map(p => p[0]);
    return !others.length || Math.min(...others) - distance >= .008;
  }).map(([, j, c]) => [j, c]);
  return pairs.filter(([j, c]) => pairs.every(([j2, c2]) => j2 === j || (j - j2) * (c - c2) > 0));
}
