import {contracts} from '../contracts.ts';
import {compare, entries, equal} from '../math.ts';
import {fitGrid} from './grid.ts';
import type {RecordData} from '../types.ts';
export type Validator = (fits: RecordData[]) => number[];

export function signature(fits: RecordData[]): unknown[] {
  return fits.map(f => ['restored', 'partial'].includes(f.status) ? [f.status, f.split, f.rows] : ['failed']);
}

export function fitGroups(groups: RecordData[], phase: number, consistent?: Validator): RecordData[] {
  const run = (g, blocks) => g.invalid ? {status: 'failed', reason: g.invalid} :
    fitGrid(g.targets, g.errors, g.bpm, g.origin + phase, undefined, 0, g.native_chords ?? [], blocks);
  const initial = groups.map(g => run(g, g.native_coordinates ?? []));
  const qualified = consistent ? new Set(consistent(initial)) : null, unique = new Map();
  groups.forEach((g, i) => {
    if (!['restored', 'partial'].includes(initial[i].status)) return;
    (g.notes ?? []).forEach((n, j) => {
      const t = initial[i].targets[j];
      if (t != null && (!qualified || qualified.has(n))) unique.set(n, [t, g.bpm]);
    });
  });
  const blocked = new Set<number>();
  const refine = () => groups.map((g, i) => {
    if (blocked.has(i)) return {status: 'failed', reason: 'unstable_neighbor_reference_rows'};
    const blocks = [];
    for (const b of g.native_coordinates ?? []) {
      blocks.push(b);
      const refs = entries<RecordData>(b.neighbor_heads ?? {}).filter(([i]) => unique.has(i) && unique.get(i)[1] === g.bpm)
        .map(([i, h]) => ({note: i, target_seconds: unique.get(i)[0], ...h}));
      if (refs.length) {
        blocks.push({...b, references: refs});
        const radius = contracts.coordinates.reference_radius_seconds;
        blocks.push({...b, references: refs, neighbors_only: true, reference_window: [Math.min(...g.targets) - radius, Math.max(...g.targets) + radius]});
      }
    }
    return run(g, blocks);
  });
  let results = refine();
  const history = groups.map(() => []);
  // Initial neighboring rows are provisional. A row refined to a different
  // time cannot continue calibrating another group at its previous time.
  // Revoke that assignment and recompute from original observations; deleting
  // provisional references makes this process finite without accepting a cycle.
  while (true) {
    const final = new Map();
    groups.forEach((g, i) => { if (['restored', 'partial'].includes(results[i].status)) (g.notes ?? []).forEach((n, j) => {
      if (results[i].targets[j] != null) final.set(n, results[i].targets[j]);
    }); });
    const invalid = [], revoked = new Set();
    groups.forEach((g, i) => {
      const local = new Set(g.notes ?? []);
      const refs = (results[i].native_coordinate_constraints ?? []).flatMap(p => p.model.references).filter(r => !local.has(r.note));
      const bad = [...new Map<string, RecordData>(refs.filter(r => !final.has(r.note) || Math.abs(final.get(r.note) - r.target_seconds) > 1e-8)
        .map(r => [`${r.note}:${r.target_seconds}`, r])).values()];
      if (bad.length) invalid.push(i);
      for (const r of bad) {
        revoked.add(r.note);
        history[i].push({note: r.note, reference_target_seconds: r.target_seconds, final_target_seconds: final.get(r.note) ?? null,
          reason: final.has(r.note) ? 'reference_row_changed' : 'reference_row_unresolved'});
      }
    });
    if (!invalid.length) break;
    let removed = false;
    for (const note of revoked) if (unique.delete(note)) removed = true;
    if (!removed) {
      // An invalid externally supplied reference cannot be replaced by a guess.
      for (const i of invalid) { blocked.add(i); for (const note of groups[i].notes ?? []) unique.delete(note); }
    }
    results = refine();
  }
  results = results.map((r, i) => history[i].length ? {...r, neighbor_reference_resolution: history[i]} : r);
  return results;
}

export function fitPhase(groups: RecordData[], uncertainty: number, consistent?: Validator): RecordData {
  const steps = Math.max(1, Math.ceil(2 * uncertainty / .001));
  const phases = uncertainty === 0 ? [0] : Array.from({length: steps + 1}, (_, i) => -uncertainty + 2 * uncertainty * i / steps);
  let best = null, winners = [];
  const trials = [];
  for (const phase of phases) {
    const fits = fitGroups(groups, phase, consistent), accepted = fits.filter(f => ['restored', 'partial'].includes(f.status));
    const count = accepted.reduce((n, f) => n + f.targets.filter(t => t != null).length, 0);
    const complexity = accepted.reduce((n, f) => n + f.split * f.targets.filter(t => t != null).length, 0);
    const supported = consistent ? consistent(fits).sort((a, b) => a - b) : null;
    const score = [supported ? supported.length : count, count, -complexity], assignment = signature(fits);
    trials.push({phase_seconds: phase, restored_targets: count, consistent_targets: score[0], subdivision_complexity: complexity});
    if (!best || compare(score, best) > 0) { best = score; winners = [{phase, fits, assignment, supported}]; }
    else if (compare(score, best) === 0) winners.push({phase, fits, assignment, supported});
  }
  if (!best[0] || winners.some(w => !equal([w.assignment, w.supported], [winners[0].assignment, winners[0].supported]))) {
    return {status: 'failed', reason: 'ambiguous_or_unsupported_song_phase', fits: groups.map(g => ({status: 'failed', reason: g.invalid ?? 'ambiguous_or_unsupported_song_phase'})), phase_trials: trials};
  }
  const lo = winners[0].phase, hi = winners.at(-1).phase, phase = (lo + hi) / 2;
  const fits = fitGroups(groups, phase, consistent);
  const unstable = !equal(signature(fits), winners[0].assignment) ? 'unstable_song_phase_assignment' :
    consistent && !equal(consistent(fits).sort((a, b) => a - b), winners[0].supported) ? 'unstable_spatial_song_phase' : null;
  if (unstable) return {status: 'failed', reason: unstable, phase_trials: trials, fits: groups.map(() => ({status: 'failed', reason: unstable}))};
  const half = uncertainty ? uncertainty / steps : 0;
  return {status: 'restored', phase, phase_range: [Math.max(-uncertainty, lo - half), Math.min(uncertainty, hi + half)],
    resolution_seconds: 2 * half, fits, phase_trials: trials, consistent_notes: winners[0].supported};
}
