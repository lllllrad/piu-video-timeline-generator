import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeScene, template} from './fixtures.ts';
import {beatView as reconstruct} from './fixtures.ts';
import {text} from '../../src/piu_timeline/derived/charts/ucs.ts';
import {transcribe} from '../../src/piu_timeline/derived/charts/transcription.ts';
import type {Interval} from '../../src/piu_timeline/derived/types.ts';

function scene(events: [number, number][], spacing: number, fps: number, lanes: number) {
  const data = JSON.parse(JSON.stringify(nativeScene(events, spacing, fps, lanes))), before = structuredClone(data), timing = template(4, 64);
  const result = reconstruct({schema: 1, data, reference: {status: 'available', song_start_seconds: 0, alignment_uncertainty_seconds: 0}, timing_text: text(timing)});
  assert.deepEqual(data, before);
  assert.deepEqual(result.notes.map(n => n.points), data.notes.map(n => n.points));
  return {data, result, timing};
}

for (const divisions of [3, 4]) for (const spacing of [20, 40, 80]) for (const fps of [30, 60, 120]) for (const lanes of [5, 10]) {
  test(`stored native observations retain every rhythm/chord through UCS: split=${divisions}, spacing=${spacing}, fps=${fps}, lanes=${lanes}`, () => {
    const events: [number, number][] = Array.from({length: 2 * divisions + 1}, (_, i) => [1 + i * .5 / divisions, i % lanes]);
    events.splice(1, 0, [1, lanes - 1]);
    const {data, result, timing} = scene(events, spacing, fps, lanes);
    assert.deepEqual(result.beat_timing.warnings, []);
    assert.equal(result.notes.length, events.length);
    const intervals = Object.fromEntries(result.notes.map((n, i) => [String(i), [n.target_seconds - n.prediction_uncertainty_seconds,
      n.target_seconds + n.prediction_uncertainty_seconds] as Interval]));
    const [, rows, accepted, failed] = transcribe(timing, intervals);
    assert.deepEqual(failed, {});
    assert.equal(Object.keys(accepted).length, events.length);
    events.forEach(([time, lane], i) => {
      assert.equal(result.notes[i].status, 'estimated');
      assert.ok(Math.abs(result.notes[i].target_seconds - time) < 1e-8);
      assert.equal(result.notes[i].lane, lane);
      assert.ok(Math.abs(rows[accepted[String(i)]][2].number() - time) < 1e-8);
      // Opaque acquisition records retain native source PTS through the same JSON contract.
      assert.ok(data.head_registration.notes[i].observations.every(o => o.source_pts_seconds === 80 + o.time));
    });
  });
}

for (const spacing of [20, 40, 80]) for (const fps of [30, 60, 120]) {
  test(`close staggers never silently collapse into chords: spacing=${spacing}, fps=${fps}`, () => {
    const events: [number, number][] = [[1, 0], [1 + 1 / 64, 1], ...Array.from({length: 8}, (_, i): [number, number] => [1 + (i + 1) * .125, (i + 1) % 5])];
    const {result} = scene(events, spacing, fps, 5);
    for (const i of [0, 1]) {
      const note = result.notes[i];
      if (note.status === 'estimated') assert.ok(Math.abs(note.target_seconds - events[i][0]) < 1e-8);
      else assert.ok(result.beat_timing.warnings.some(w => w.note === i));
    }
  });
}
