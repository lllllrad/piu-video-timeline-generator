import test from 'node:test';
import assert from 'node:assert/strict';
import {grid, parse, text, type Document} from '../../src/piu_timeline/derived/charts/ucs.ts';
import {transcribe} from '../../src/piu_timeline/derived/charts/transcription.ts';
import {q} from '../../src/piu_timeline/derived/charts/rational.ts';
import type {Interval} from '../../src/piu_timeline/derived/types.ts';
import {template} from './fixtures.ts';

const intervals = (values: number[], error: number): Record<string, Interval> => Object.fromEntries(values.map((t, i) => [String(i), [t - error, t + error]]));
function duration(doc: Document) {
  const settings = Object.fromEntries(doc.sections.flatMap(s => s.directives));
  return grid(doc).at(-1)[2].add(q(60).div(q(settings.BPM).mul(q(settings.Split)))).toString();
}

test('measures choose their own smallest supported split and share a chord row', () => {
  const source = template(), points = intervals([.25, .75, .754, 2 + 1 / 6, 2 + 1 / 3], .006), before = structuredClone(points);
  const [doc, rows, accepted, failed, proof] = transcribe(source, points);
  assert.deepEqual(points, before);
  assert.deepEqual(proof.measures.map(m => m.split), [2, 3]);
  assert.equal(accepted['1'], accepted['2']);
  assert.equal(rows[accepted['1']][2].toString(), '3/4');
  assert.deepEqual(failed, {});
  assert.equal(duration(doc), duration(source));
  assert.deepEqual(parse(text(doc)), doc);
});
test('a fine grid cannot choose a nearest row inside an ambiguous interval', () => {
  const [, , accepted, failed, proof] = transcribe(template(), intervals([.75, 1], .02));
  assert.equal(Object.keys(accepted).length, 2);
  assert.deepEqual(failed, {});
  assert.equal(proof.measures[0].split, 2);
  assert.equal(proof.measures[0].tested_splits.find(s => s.split === 48).unique_endpoints, 0);
});
test('absolute timing tolerance does not depend on split or row duration at document edges', () => {
  for (const source of [template(1, 4), template(48, 1)]) {
    const [, , accepted, failed, proof] = transcribe(source, {'0': [-.001, .009]});
    assert.ok(Object.hasOwn(accepted, '0'));
    assert.deepEqual(failed, {});
    assert.equal(proof.measures[0].status, 'restored');
  }
  for (const bpm of [60, 120, 240]) for (const [center, expected] of [[.012, true], [.0121, false]] as const) {
    const source = parse(text(template(1, 4)).replace('BPM=120', `BPM=${bpm}`));
    const [, , accepted, failed] = transcribe(source, {'0': [-.001, 2 * center + .001]});
    assert.equal(Object.hasOwn(accepted, '0'), expected);
    assert.equal(Object.hasOwn(failed, '0'), !expected);
  }
});
test('jitter around a measure boundary preserves a single chord', () => {
  const [, rows, accepted, failed] = transcribe(template(), intervals([1.999, 2.001], .005));
  assert.deepEqual(failed, {});
  assert.equal(accepted['0'], accepted['1']);
  assert.equal(rows[accepted['0']][2].toString(), '2');
});
test('a neighboring finer measure can invalidate an ambiguous boundary placement', () => {
  const [, , accepted, failed, proof] = transcribe(template(), {'0': [1.988, 2.010], '1': [2.0077125, 2.0079125]});
  assert.equal(Object.hasOwn(accepted, '0'), false);
  assert.match(failed['0'], /across measure grids/);
  assert.ok(Object.hasOwn(accepted, '1'));
  assert.equal(proof.measures[1].split, 64);
});
test('tempo, delay and fractional measure boundaries retain exact duration', () => {
  const source = parse(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=90\n:Beat=4\n:Split=2\n' + '.....\n'.repeat(3) + ':BPM=180\n:Delay=10\n:Split=3\n' + '.....\n'.repeat(12));
  const [doc, rows, , , proof] = transcribe(source, {});
  assert.equal(rows[0][2].toString(), '9/100');
  const boundary = doc.sections.findIndex(s => Object.fromEntries(s.directives).BPM === '180');
  assert.equal(rows.find(r => r[0] === boundary)[2].toString(), '17/20');
  assert.equal(duration(doc), duration(source));
  assert.deepEqual(proof.measures.map(m => m.beat_offset), ['0', '3/2', '0']);
  assert.ok(rows.slice(1).every((r, i) => r[2].number() > rows[i][2].number()));
});
test('every target outside the template has an explicit failure', () => {
  const points = {'0': [-1.01, -.99], '1': [5, 5.01]} as Record<string, Interval>;
  const [, , accepted, failed] = transcribe(template(), points);
  assert.deepEqual(accepted, {});
  assert.deepEqual(Object.keys(failed).sort(), Object.keys(points).sort());
});
