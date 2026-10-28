import test from 'node:test';
import assert from 'node:assert/strict';
import {expanded, grid, parse, text} from '../../src/piu_timeline/derived/charts/ucs.ts';
import {validate} from '../../src/piu_timeline/derived/charts/assertions.ts';

const timing = ':Format=1\n:Mode=Single\n:BPM=120\n:Delay=90\n:Beat=4\n:Split=2\n.....\n.....\n:BPM=180\n:Delay=-10\n:Beat=3\n:Split=3\n.....\n.....\n';

test('UCS sections retain exact tempo/delay timing and round-trip directives', () => {
  const doc = parse(timing);
  assert.deepEqual(grid(doc).map(r => r[2].toString()), ['9/100', '17/50', '29/50', '311/450']);
  assert.deepEqual(parse(text(doc)), doc);
});

test('densification preserves original row times while changing lane width', () => {
  const doc = parse(timing), wide = expanded(doc, 10, 48), rows = grid(wide);
  assert.equal(Object.fromEntries(wide.header).Mode, 'Double');
  assert.ok(wide.sections.every(s => s.rows.every(r => r.length === 10)));
  for (const [si, ri, time] of grid(doc)) {
    const before = Number(Object.fromEntries(doc.sections[si].directives).Split), after = Number(Object.fromEntries(wide.sections[si].directives).Split);
    assert.ok(rows.some(([s, r, t]) => s === si && r === ri * after / before && t.toString() === time.toString()));
  }
  assert.deepEqual(parse(text(wide)), wide);
  assert.throws(() => expanded(parse(timing.replace('.....', 'X....')), 5), /empty timing template/);
});

for (const [before, after] of [['BPM=120', 'BPM=0'], ['Split=2', 'Split=1.5'], ['Beat=4', 'Beat=0'],
  ['.....', '....'], ['.....', 'Z....'], ['BPM=120', 'BPM=nan']]) {
  test(`invalid UCS timing/notes are rejected: ${after}`, () => assert.throws(() => parse(timing.replaceAll(before, after))));
}
test('unknown UCS directives fail explicitly', () => assert.throws(() => parse(timing + ':Speed=2\n.....\n')));

const fact = () => ({id: 'reviewed-chord', start_seconds: 0, end_seconds: 1, cells: {'0': 'X', '1': 'X'}, reason: 'Both panels require the same input time.'});
const document = (rows: string) => parse(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=1\n' + rows);
test('separate rows cannot satisfy a reviewed simultaneous chord', () => {
  validate(document('XX...\n.....\n'), [fact()]);
  assert.throws(() => validate(document('X....\n.X...\n'), [fact()]), /reviewed-chord failed/);
});
test('malformed, duplicate and out-of-scope reviewed assertions fail', () => {
  for (const change of [{start_seconds: NaN}, {end_seconds: 0}, {cells: {'5': 'X'}}, {cells: {'0': '?'}}, {reason: ''}]) {
    assert.throws(() => validate(document('XX...\n'), [{...fact(), ...change}]));
  }
  assert.throws(() => validate(document('XX...\n'), [fact(), fact()]));
});
