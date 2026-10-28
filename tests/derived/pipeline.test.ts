import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, readFileSync, writeFileSync, rmSync, statSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {prepare, current, type PresentationInput} from '../../src/piu_timeline/derived/pipeline/presentation.ts';
import {parseData, stringifyData} from '../../src/piu_timeline/derived/json.ts';
import {fingerprint, Store} from '../../src/piu_timeline/derived/pipeline/store.ts';

function input(): PresentationInput {
  const frames = [.9, .92, .94, .96].map(t => ({playback_seconds: t, source_pts_seconds: t + 80, notes: [], combo: null, combo_confidence: 0}));
  return {schema: 1, data: {song: 'Example', media: {path: '/missing/original.mkv', mtime_ns: 1780000000000000001n},
    start_seconds: 0, end_seconds: 2, notes: [{lane: 0, status: 'estimated', target_seconds: 1, prediction_uncertainty_seconds: .01, points: [[.9, 100]]}],
    matches: [], combo_events: [], judgment_events: [], hold_analysis: {holds: []}, limitations: [],
    layout: {receptor_y: .2, lanes: Array.from({length: 5}, (_, i) => ({x: .1 + .15 * i}))}, analysis_width: 650, analysis_height: 365},
    observations: {frames, visibility_frames: frames.map(({playback_seconds, source_pts_seconds, notes}) => ({playback_seconds, source_pts_seconds, notes})),
      occluders: [], native_body_risk_available: false, pre_hold_proofs: {}}};
}
const manifest = (directory: string) => parseData(readFileSync(join(directory, 'derived-stages/manifest.json'), 'utf8')).stages;

test('prepared observations replay entirely without source media or native libraries and retain warnings', () => {
  const request = input(), before = stringifyData(request), report = prepare(request);
  assert.equal(stringifyData(request), before);
  assert.equal(report.media.mtime_ns, 1780000000000000001n);
  assert.equal(report.notes.length, 1);
  assert.equal(report.timing_ranges.notes['0'].status, 'unknown');
  assert.ok(report.recognition_diagnostics.warnings.some(w => w.reason === 'timing_evidence_unresolved'));
  assert.equal(Object.hasOwn(report, 'visual_channels'), false);
});

test('four full observation channels survive consumer projections unchanged', () => {
  const request = input();
  request.data.visual_channels = {popup: {combo_events: [], judgment_events: [], observations: [[null, 0, null]]},
    receptors: {events: [], observations: [[[false], [.1], false]], onsets: 0}, motion: {observations: [[[0, .1, .8, .9]]]},
    processing: {notes: [], counts: {}, body_observations: [[]]}, note_types: {notes: []}, timeline: {frames: [[.9, 80.9]]}};
  const before = structuredClone(request.data.visual_channels), report = prepare(request);
  assert.deepEqual(report.visual_channels, before);
});

test('stage reuse follows consumed inputs; title changes do not rerun inference and counter reads do not rerun visibility', () => {
  const directory = mkdtempSync(join(tmpdir(), 'piu-stages-'));
  try {
    const request = input(); prepare(request, directory);
    assert.ok(manifest(directory).every(s => !s.reused));
    request.data.song = 'Updated title';
    assert.equal(prepare(request, directory).song, 'Updated title');
    assert.ok(manifest(directory).every(s => s.reused));
    request.observations.frames[0].combo_confidence = .9;
    prepare(request, directory);
    assert.deepEqual(manifest(directory).filter(s => !s.reused).map(s => s.stage), ['timing-ranges']);
    request.observations.visibility_frames[0].notes = [{lane: 0, x: .1, y: .8}];
    prepare(request, directory);
    assert.deepEqual(manifest(directory).filter(s => !s.reused).map(s => s.stage), ['visibility']);
  } finally {rmSync(directory, {recursive: true, force: true});}
});

test('stale configured pixel evidence and mismatched source timelines fail explicitly', () => {
  const request = input();
  request.observations.configured_processing = {input: {notes: []}, output: {notes: []}};
  assert.throws(() => prepare(request), /different interpretation inputs/);
  delete request.observations.configured_processing;
  request.observations.visibility_frames[0].source_pts_seconds += .001;
  assert.throws(() => prepare(request), /different source timelines/);
});

test('incomplete game geometry remains an explicit warning while the observation view stays usable', () => {
  const request = input(); request.data.layout.lanes = [{x: .1}];
  const report = prepare(request);
  assert.ok(report.visibility_diagnostics.warnings.some(w => w.reason === 'visibility_geometry_unavailable'));
  assert.ok(report.recognition_diagnostics.warnings.some(w => w.reason === 'visibility_geometry_unavailable'));
});

test('artwork identity comparisons preserve opaque source integers and object-key independence', () => {
  const request = input(), effect = {id: 'art', kind: 'decorative_note_art', review_status: 'pending', playback_start_seconds: .5, playback_end_seconds: .8,
    source: {mtime_ns: 1780000000000000001n, size_bytes: 100}};
  request.data.chart_policy = {regions: [], gimmick_candidates: [effect]};
  request.data.object_interpretation = {effects: [{...effect, source: {size_bytes: 100, mtime_ns: 1780000000000000001n}}], warnings: []};
  const report = prepare(request);
  assert.deepEqual(report.object_interpretation.warnings, []);
  assert.ok(!report.recognition_diagnostics.warnings.some(w => w.reason === 'decorative_art_interpretation_missing'));
  assert.ok(stringifyData(report).includes('1780000000000000001'));
});

test('maintenance rejects changed source artifacts without reading their frame payload', () => {
  const directory = mkdtempSync(join(tmpdir(), 'piu-stages-'));
  try {
    const path = join(directory, 'frames.jsonl'); writeFileSync(path, 'opaque acquired frame payload');
    const stat = statSync(path, {bigint: true}), request = input();
    request.observations.source_artifacts = {'frames.jsonl': [Number(stat.size), stat.mtimeNs]};
    prepare(request, directory); assert.equal(current(directory), true);
    writeFileSync(path, 'different acquired frame payload');
    assert.equal(current(directory), false);
  } finally {rmSync(directory, {recursive: true, force: true});}
});

test('corrupted stage output cannot be accepted or silently rebuilt', () => {
  const directory = mkdtempSync(join(tmpdir(), 'piu-stages-'));
  try {
    prepare(input(), directory);
    const path = join(directory, 'derived-stages/hold-view.json'), artifact = parseData(readFileSync(path, 'utf8'));
    artifact.output.notes = []; writeFileSync(path, stringifyData(artifact));
    assert.throws(() => prepare(input(), directory), /Corrupt derived stage artifact/);
  } finally {rmSync(directory, {recursive: true, force: true});}
});

test('artifact promotion preserves local references, opaque integers and producer invalidation', () => {
  const directory = mkdtempSync(join(tmpdir(), 'piu-stages-'));
  try {
    const store = new Store(directory), source = {path: join(directory, 'proof.json')};
    const first = store.run('example', 'producer-a', source, () => ({path: source.path, pts: 1780000000000000001n}));
    const again = new Store(directory).run('example', 'producer-a', source, () => {throw new Error('must reuse');});
    assert.deepEqual(again, first);
    assert.equal(new Store(directory).run('example', 'producer-b', source, () => ({updated: true})).updated, true);
    assert.equal(fingerprint(parseData(stringifyData(first))), fingerprint(first));
  } finally {rmSync(directory, {recursive: true, force: true});}
});

test('standalone presentation CLI replays saved JSON and leaves old output intact on failure', () => {
  const directory = mkdtempSync(join(tmpdir(), 'piu-stages-'));
  try {
    const source = join(directory, 'input.json'), output = join(directory, 'report-data.json');
    writeFileSync(source, stringifyData(input()));
    const run = () => spawnSync(process.execPath, [resolve('src/piu_timeline/derived/cli.ts'), 'presentation', source, output],
      {encoding: 'utf8', env: {...process.env, PATH: directory}});
    assert.equal(run().status, 0);
    const before = readFileSync(output, 'utf8'); assert.ok(before.includes('1780000000000000001'));
    writeFileSync(source, '{"schema":99}'); assert.equal(run().status, 1);
    assert.equal(readFileSync(output, 'utf8'), before);
  } finally {rmSync(directory, {recursive: true, force: true});}
});
