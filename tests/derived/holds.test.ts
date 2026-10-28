import test from 'node:test';
import assert from 'node:assert/strict';
import {simplify} from '../../src/piu_timeline/derived/charts/holds.ts';
import type {Interval, RecordData} from '../../src/piu_timeline/derived/types.ts';
import {template} from './fixtures.ts';
import {attach, contextualSupport, recognitionWindow, receptorRuns} from '../../src/piu_timeline/derived/hold_state.ts';

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

test('a common flash preserves the measured onset bracket without inventing another press', () => {
  const frames = [false, false, null, true, true, null, true, true].map((lit, i) => ({playback_seconds: i / 60,
    source_pts_seconds: 40 + i / 60, receptor_lit: [lit], common_receptor_flash: lit === null}));
  const before = structuredClone(frames), runs = receptorRuns(frames), lit = runs.filter(r => r.lit === true);
  assert.deepEqual(frames, before);
  assert.deepEqual(lit[0].onset_range, [1 / 60, 3 / 60]);
  assert.deepEqual(lit[0].onset_source_pts_seconds, [40 + 1 / 60, 40 + 3 / 60]);
  assert.equal(lit[1].onset_range, null);
  assert.equal(lit[0].corroborating_lit_frames_after_flash, 1);
});
test('dim contextual hold responses require independent geometry and never become press/release times', () => {
  const frames = Array.from({length: 51}, (_, i) => ({playback_seconds: i / 50, source_pts_seconds: 40 + i / 50,
    receptor_lit: Array(5).fill(false), bodies: [{lane: 2, top: 20, bottom: 80}],
    receptor_white_fraction: Array.from({length: 5}, (_, lane) => lane === 2 && [30, 31].includes(i) ? .45 : .1)}));
  const holds = [{lane: 2, start_range: [.5, .51], start_censored: false, end_range: [.7, .71], tail_note: null, covered_notes: []}];
  const data = {notes: [], combo_events: [{delta: 1, lower_seconds: .59, upper_seconds: .6}]}, before = structuredClone({frames, holds});
  assert.deepEqual(contextualSupport(data, frames, 20, 20, [], true), {});
  const result = attach(data, frames, holds, {receptor: 20, spacing: 20, note_scale: 1, edge_tolerance: .55}, true);
  assert.deepEqual({frames, holds}, before);
  assert.deepEqual(result[0].input.recognition_envelope, [.6, .62]);
  assert.equal(result[0].input.segments[0].contextual_frames, 2);
  assert.equal(result[0].input.press_range, null); assert.equal(result[0].input.release_range, null);
});
test('the following independent tap bounds a hold response window', () => {
  const data = {notes: [{lane: 0, status: 'estimated', target_seconds: .7, velocity_pixels_per_second: -100},
    {lane: 0, status: 'estimated', target_seconds: .73, prediction_uncertainty_seconds: .01}]};
  const hold = {lane: 0, start_range: [.5, .51], start_censored: false, end_range: [.7, .71], tail_note: 0, covered_notes: [0]};
  assert.deepEqual(recognitionWindow(data, hold, {receptor: 20, spacing: 20, note_scale: 1, edge_tolerance: .55}), [.5, .72]);
});
