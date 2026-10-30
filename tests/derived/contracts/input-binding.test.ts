/** Detached results must retain the exact source they were calculated from. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {capture, materialize as coordinates} from '../../../src/piu_timeline/derived/stages/coordinates.ts';
import {resolve, materialize as nativeTiming} from '../../../src/piu_timeline/derived/stages/native_timing.ts';
import {input, reconstruct, materialize as beats} from '../../../src/piu_timeline/derived/beats/stage.ts';
import {artifact, boundArtifact} from '../../../src/piu_timeline/derived/stages/contracts.ts';
import {input as inspectionInput} from '../../../src/piu_timeline/derived/pipeline/contracts.ts';
import {prepare, preview} from '../../../src/piu_timeline/derived/pipeline/presentation.ts';
import {applyResult, result, materialize} from '../../../src/piu_timeline/derived/pipeline/composition.ts';
import {processing} from '../../../src/piu_timeline/derived/pipeline/inputs.ts';
import {parseData, stringifyData} from '../../../src/piu_timeline/derived/json.ts';
import {domain} from '../beats/fixtures.ts';

const timing = ':Format=1\n:Mode=Single\n:BPM=120\n:Beat=4\n:Split=4\n' + '.....\n'.repeat(32);
function beatRequest(data = domain(), root?: string) {
  const source = capture(data, root);
  return input(source, resolve(source), {status: 'available', song_start_seconds: 1, alignment_uncertainty_seconds: 0}, timing);
}
function inspection(root?: string) {
  return inspectionInput({
    ...domain(), start_seconds: 0, end_seconds: 3, matches: [], combo_events: [], judgment_events: [],
    hold_analysis: {holds: []}, limitations: [], media: {path: '/missing/source.mkv', mtime_ns: 1234567890123456789n},
  }, {frames: [], visibility_frames: [], occluders: [], native_body_risk_available: false, pre_hold_proofs: {}}, root);
}

test('same note IDs and count cannot disguise a different coordinate source', () => {
  const a = capture(domain()), changed = domain();
  changed.notes[0].points[0][1] += 1;
  const b = capture(changed);
  assert.equal(a.observations.data.notes.length, b.observations.data.notes.length);
  assert.throws(() => coordinates({...a, observations: b.observations}), /different inputs/);
  assert.throws(() => nativeTiming(b, resolve(a)), /different inputs/);
});

test('musical output rejects changed coordinates, reference and UCS text', () => {
  const a = beatRequest(), output = reconstruct(a), changed = domain();
  changed.notes[0].points[0][1] += 1;
  const b = beatRequest(changed);
  for (const wrong of [b, {...a, reference: {...a.reference, song_start_seconds: 2}}, {...a, timing_text: timing + '.....\n'}]) {
    assert.throws(() => beats(wrong, output), /different inputs/);
  }
  const unbound = artifact('beats', output.data);
  assert.throws(() => beats(a, unbound as never), /different inputs/);
});

test('inspection rejects a result from another observation timeline or track set', () => {
  const request = inspection(), output = prepare(request), changed = structuredClone(request);
  const tracks = structuredClone(changed.source.tracks.data) as any;
  tracks.notes[0].points[0][1] += 1;
  changed.source.tracks = artifact('inspection-tracks', tracks);
  assert.throws(() => materialize(changed, output), /different inputs/);
  const otherFrames = {...request, observations: {...request.observations, frames: [{playback_seconds: 1, source_pts_seconds: 9}]}};
  assert.throws(() => materialize(otherFrames, output), /different inputs/);
});

test('directory promotion preserves bindings, local evidence links and opaque source identity', () => {
  const before = '/tmp/example/play/segment-001.build-generic/', after = '/tmp/example/play/segment-001/';
  const data = domain();
  data.notes[0].trace = before + 'evidence/cap.json';
  const request = beatRequest(data, before), output = reconstruct(request), viewRequest = inspection(before);
  viewRequest.source.metadata = {...viewRequest.source.metadata, evidence: before + 'evidence/source.json'};
  const viewOutput = prepare(viewRequest);
  const encoded = stringifyData({request, output, viewRequest, viewOutput}).replaceAll(before, after);
  const moved = parseData(encoded);
  const noteView = beats(moved.request, moved.output);
  assert.equal(noteView.notes[0].trace, after + 'evidence/cap.json');
  const display = materialize(moved.viewRequest, moved.viewOutput);
  assert.equal(display.evidence, after + 'evidence/source.json');
  assert.equal(display.media.mtime_ns, 1234567890123456789n);
});

test('prepared native measurements survive when no prior channel map exists', () => {
  const request = inspection(), view = materialize(request, preview(request));
  const measured = {note: 0, status: 'passed_target', samples: [{source_pts_seconds: 81, state: 'present'}]};
  request.observations = {...request.observations, configured_processing: {input: processing(view), output: {notes: [measured]}}};
  const output = prepare(request), display = materialize(request, output);
  assert.deepEqual(display.visual_channels.processing.notes[0].samples, measured.samples);
  assert.equal(display.visual_channels.processing.notes[0].status, 'passed_target');
  const stage = result('configured-processing', {notes: []}, {visual_channels: {processing: {notes: [measured]}}});
  assert.deepEqual(applyResult({notes: []}, stage).visual_channels.processing.notes, [measured]);
  const missing = boundArtifact('inspection', request, {stages: output.data.stages.filter(s => s.stage !== 'configured-processing')});
  assert.throws(() => materialize(request, missing), /Incomplete/);
});

test('judgment results cannot masquerade as the broader inspection association input', () => {
  const request = inspection();
  request.source.judgments = artifact('judgment-associations', {}) as never;
  assert.throws(() => prepare(request), /Expected inspection-associations/);
});
