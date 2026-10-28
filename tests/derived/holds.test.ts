import test from 'node:test';
import assert from 'node:assert/strict';
import {simplify} from '../../src/piu_timeline/derived/charts/holds.ts';
import type {Interval, RecordData} from '../../src/piu_timeline/derived/types.ts';
import {template} from './fixtures.ts';

function fixture(gaps = [.04, .04]) {
  const observed: RecordData[] = [], edges: Record<string, Interval> = {}, notes: RecordData[] = [];
  let start = .25;
  [0, ...gaps].forEach((gap, i) => {
    if (i) start += gap;
    const end = start + .25;
    observed.push({note: i, lane: 0, kind: 'hold', observed_target_range: [start - .002, start + .002], observed_end_range: [end - .002, end + .002]});
    edges[`${i},head`] = [start - .002, start + .002]; edges[`${i},tail`] = [end - .002, end + .002];
    notes.push({lane: 0, target_seconds: start, prediction_uncertainty_seconds: .002});
    start = end;
  });
  return {observed, edges, notes};
}
test('continuous held state supports a short larger gap without swallowing a tap', () => {
  const {observed, edges, notes} = fixture([.2]);
  const run = {lane: 0, lit: true, frames: 30, start_seconds: 10.4, end_seconds: 10.8, first_source_pts_seconds: 30.4, last_source_pts_seconds: 30.8};
  const [result, , proof] = simplify(template(), observed, edges, notes, 10, [run]);
  assert.equal(result.length, 1);
  assert.equal(proof.merges[0].bridged_gaps[0].basis, 'continuous_held_state');
  assert.deepEqual(proof.merges[0].bridged_gaps[0].held_state_evidence.source_pts_range, [30.4, 30.8]);
  for (const change of [{lane: 1}, {lit: false}, {lit: null}, {start_seconds: 10.51}, {end_seconds: 10.69}, {frames: 1}]) {
    assert.equal(simplify(template(), observed, edges, notes, 10, [{...run, ...change}])[0].length, 2);
  }
  notes.push({lane: 0, target_seconds: 10.6, prediction_uncertainty_seconds: .01});
  assert.equal(simplify(template(), observed, edges, notes, 10, [run])[0].length, 2);
});
test('proven hold components permit merging while pending cap roles block it', () => {
  const {observed, edges, notes} = fixture([.04]);
  const component = {lane: 0, target_seconds: .5, prediction_uncertainty_seconds: .01, note_type: 'hold_component', reason: 'long_note_body_or_tail'};
  notes.push(component);
  assert.equal(simplify(template(), observed, edges, notes, 0)[0].length, 1);
  component.reason = 'observed_hold_tail_pending_geometry';
  assert.equal(simplify(template(), observed, edges, notes, 0)[0].length, 2);
});
test('chain merges retain every original interval without mutating their source', () => {
  const f = fixture(), before = structuredClone(f);
  const [result, edges, proof] = simplify(template(), f.observed, f.edges, f.notes, 0);
  assert.deepEqual(f, before);
  assert.equal(result.length, 1);
  assert.deepEqual(edges, {'0,head': f.edges['0,head'], '0,tail': f.edges['2,tail']});
  assert.deepEqual(result[0].source_hold_intervals.map(o => o.note), [0, 1, 2]);
  assert.equal(proof.merges[0].bridged_gaps.length, 2);
  assert.equal(proof.policy.hold_tick_equivalence, 'unverified');
});
test('a tap or unresolved head blocks bridging even when not exportable', () => {
  for (const target of [.52, null]) {
    const f = fixture([.04]); f.notes.push({lane: 0, target_seconds: target, prediction_uncertainty_seconds: .01});
    const [result, edges, proof] = simplify(template(), f.observed, f.edges, f.notes, 0);
    assert.equal(result.length, 2); assert.deepEqual(edges, f.edges); assert.deepEqual(proof.merges, []);
  }
});
test('long gaps and contained duplicates cannot be simplified', () => {
  const f = fixture([.2]);
  assert.equal(simplify(template(), f.observed, f.edges, f.notes, 0)[0].length, 2);
  f.edges['1,head'] = [.3, .304]; f.edges['1,tail'] = [.4, .404];
  assert.equal(simplify(template(), f.observed, f.edges, f.notes, 0)[0].length, 2);
});
test('fast tempo tightens the hold bridging limit', () => {
  const f = fixture([.08]), fast = template();
  assert.equal(simplify(template(), f.observed, f.edges, f.notes, 0)[0].length, 1);
  fast.sections[0].directives = fast.sections[0].directives.map(([k, v]) => [k, k === 'BPM' ? '240' : v]);
  assert.equal(simplify(fast, f.observed, f.edges, f.notes, 0)[0].length, 2);
});
