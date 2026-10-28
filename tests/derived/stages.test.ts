import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, readFileSync, writeFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {grid, parse, text} from '../../src/piu_timeline/derived/charts/ucs.ts';
import {transcribe} from '../../src/piu_timeline/derived/charts/transcription.ts';
import {reconstruct, type BeatInput} from '../../src/piu_timeline/derived/beats/stage.ts';
import {render} from '../../src/piu_timeline/derived/report.ts';
import type {Interval} from '../../src/piu_timeline/derived/types.ts';
import {parseData, stringifyData} from '../../src/piu_timeline/derived/json.ts';
import {associate} from '../../src/piu_timeline/derived/association.ts';
import {attachRecoveredLabels} from '../../src/piu_timeline/derived/labels.ts';
import {recoverAggregates} from '../../src/piu_timeline/derived/recovery.ts';

const timing = ':Format=1\n:Mode=Single\n:BPM=137.5\n:Delay=-12.5\n:Beat=4\n:Split=3\n' + '.....\n'.repeat(1200);

test('long decimal-tempo grids retain exact rational seconds across sections', () => {
  const rows = grid(parse(timing + ':BPM=123.456\n:Delay=7.25\n.....\n'));
  assert.equal(rows[1200][2].toString(), '7679769/44000');
  assert.equal(text(parse(timing)), timing);
});

test('a single bounded observation on either side of a measure boundary is never silently dropped', () => {
  const source = parse(':Format=1\n:Mode=Single\n:BPM=120\n:Beat=4\n:Split=4\n' + '.....\n'.repeat(32));
  const endpoints: Record<string, Interval> = {left: [1.874, 1.876], chordA: [1.999, 2.001], chordB: [1.999, 2.001], unsupported: [2.136999, 2.137001]};
  const [doc, , accepted, failed, proof] = transcribe(source, endpoints) as any[];
  assert.equal(accepted.chordA, accepted.chordB);
  assert.ok(accepted.left < accepted.chordA);
  assert.ok(failed.unsupported);
  assert.equal(Object.keys(accepted).length + Object.keys(failed).length, Object.keys(endpoints).length);
  assert.equal(proof.measures[0].split, 4);
  assert.equal(grid(doc)[accepted.chordA][2].toString(), '2');
});

function input(): BeatInput {
  return {schema: 1, reference: {status: 'available', song_start_seconds: 10, alignment_uncertainty_seconds: 0},
    timing_text: ':Format=1\n:Mode=Single\n:BPM=120\n:Beat=4\n:Split=4\n' + '.....\n'.repeat(32),
    data: {notes: [10.001, 10.126, 10.126, 10.251].map((target, i) => ({lane: i, points: [[9.9, 200]], status: 'estimated',
      target_seconds: target, prediction_uncertainty_seconds: .003}))}};
}

test('beat reconstruction is pure, retains native positions and never returns acquisition identity', () => {
  const source = input(), original = structuredClone(source), result = reconstruct(source);
  assert.deepEqual(source, original);
  assert.deepEqual(result.notes.map(n => n.target_seconds), [10, 10.125, 10.125, 10.25]);
  assert.deepEqual(result.notes.map(n => n.points), source.data.notes.map(n => n.points));
  assert.deepEqual(Object.keys(result).sort(), ['beat_timing', 'notes', 'timing_reconstruction']);
  assert.equal(result.beat_timing.status, 'restored');
});

test('malformed observation contracts fail before inference', () => {
  const source = input();
  source.data.notes[0].points = [[9.9, 200], [9.8, 190]];
  assert.throws(() => reconstruct(source), /Invalid native positions/);
  source.schema = 2 as any;
  assert.throws(() => reconstruct(source), /Unsupported beat-stage/);
});

test('opaque provenance integers survive numerical stages without a floating-point conversion', () => {
  const serialized = JSON.stringify(input()).replace('"lane":0', '"lane":0,"source_identity":1780000000000000001');
  const source = parseData(serialized), result = reconstruct(source);
  assert.equal(typeof result.notes[0].source_identity, 'bigint');
  assert.ok(stringifyData(result).includes('"source_identity":1780000000000000001'));
  assert.deepEqual(result.notes.map(n => n.target_seconds), [10, 10.125, 10.125, 10.25]);
});

test('standalone replay needs no Python and preserves an existing output on failure', () => {
  const directory = mkdtempSync(join(tmpdir(), 'piu-derived-'));
  try {
    const source = join(directory, 'input.json'), output = join(directory, 'output.json');
    writeFileSync(source, JSON.stringify(input()));
    const cli = resolve('src/piu_timeline/derived/cli.ts');
    const run = () => spawnSync(process.execPath, [cli, 'beats', source, output], {encoding: 'utf8', env: {...process.env, PATH: directory}});
    assert.equal(run().status, 0);
    const before = readFileSync(output, 'utf8');
    assert.equal(JSON.parse(before).beat_timing.status, 'restored');
    writeFileSync(source, '{"schema":99}');
    assert.equal(run().status, 1);
    assert.equal(readFileSync(output, 'utf8'), before);
  } finally { rmSync(directory, {recursive: true, force: true}); }
});

test('rendering accepts opaque analysis JSON without rounding source identity or allowing script injection', () => {
  const data = '{"media":{"mtime_ns":1780000000000000001},"song":"</script><img>"}';
  const html = render(data, '</title><img>', 'S20', 'source%20file.mkv');
  assert.ok(html.includes('1780000000000000001'));
  assert.ok(!html.includes('<img>'));
  assert.ok(html.includes('\\u003c/script\\u003e'));
});

test('zero is a measured chart time and keeps its place before later rows', () => {
  const notes = [{lane: 0, status: 'estimated', target_seconds: .5}, {lane: 0, status: 'estimated', target_seconds: 0}];
  const events = [0, .5].map(t => ({delta: 1, status: 'candidate', lower_seconds: t - .01, upper_seconds: t + .01}));
  assert.deepEqual(associate(notes, events).map(m => [m.note, m.combo_event]), [[1, 0], [0, 1]]);
});

test('an explicitly unknown native word status cannot become a recovered label', () => {
  const result = attachRecoveredLabels({matches: [{note: 0, combo_event: 0, target_seconds: 1, recovery_method: 'independent_lane_onset'}],
    combo_events: [{delta: 1, status: 'matched', lower_seconds: .99, upper_seconds: 1.01}],
    judgment_events: [{label: 'PERFECT', detection_status: null, status: 'excluded', lower_seconds: .995, upper_seconds: 1.005}]});
  assert.equal(result.matches[0].judgment_label, undefined);
});

test('separate aggregate refreshes retain their own local offset hypotheses', () => {
  const notes = [1, 1.04, 3, 3.04, .8, 2.8].map((t, i) => ({lane: Math.min(i, 4), status: 'estimated', target_seconds: t, prediction_uncertainty_seconds: .01}));
  const data = {notes, matches: [{note: 4, target_seconds: .8, observation_lower_seconds: .89, observation_upper_seconds: .91},
    {note: 5, target_seconds: 2.8, observation_lower_seconds: 2.99, observation_upper_seconds: 3.01}],
    combo_events: [{delta: 2, lower_seconds: 1.09, upper_seconds: 1.15}, {delta: 2, lower_seconds: 3.19, upper_seconds: 3.25}],
    hold_analysis: {receptor_runs: [1.09, 1.09, 3.19, 3.19].map((t, lane) => ({lane, lit: true, frames: 3, onset_range: [t, t + .01], start_seconds: t, end_seconds: t + .06}))}};
  const [matches, recovered] = recoverAggregates(data);
  assert.deepEqual(recovered, [0, 1, 2, 3]);
  assert.ok(matches.find(m => m.note === 0).aggregate_target_offset_hypotheses_seconds.some(v => Math.abs(v - .1) < 1e-9));
  assert.ok(matches.find(m => m.note === 2).aggregate_target_offset_hypotheses_seconds.some(v => Math.abs(v - .2) < 1e-9));
});
