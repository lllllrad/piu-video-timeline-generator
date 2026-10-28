import test from 'node:test';
import assert from 'node:assert/strict';
import {fitGrid} from '../../src/piu_timeline/derived/beats/grid.ts';
import {fitPhase} from '../../src/piu_timeline/derived/beats/phase.ts';

test('regular quarters use the smallest split and exact rows', () => {
  const result = fitGrid([10.001, 10.124, 10.251, 10.374], Array(4).fill(.003), 120, 10);
  assert.equal(result.status, 'restored'); assert.equal(result.split, 4);
  assert.deepEqual(result.targets, [10, 10.125, 10.25, 10.375]);
});
test('triplets and quarters share a natural twelve-way split', () => {
  assert.equal(fitGrid([10, 10.125, 10 + 1 / 6, 10 + 1 / 3], Array(4).fill(.0001), 120, 10).split, 12);
});
test('uncertain and unsupported rows fail explicitly', () => {
  assert.equal(fitGrid([10.25], [.26], 120, 10).reason, 'ambiguous_beat_rows');
  assert.equal(fitGrid([10.137], [.000001], 120, 10).reason, 'no_natural_beat_subdivision');
});
test('an unresolved row cannot collapse onto an independent known row', () => {
  const result = fitGrid([10.01, 10.11], [.12, .12], 120, 10);
  assert.equal(result.status, 'partial'); assert.deepEqual(result.rows.map(r => r === null ? null : r + 0), [0, null]); assert.deepEqual(result.targets, [10, null]);
});
test('one common phase is required instead of independently shifting notes', () => {
  const result = fitGrid([10.01, 10.135], [.001, .001], 120, 10, undefined, .02);
  assert.equal(result.split, 4); assert.ok(Math.abs((result.phase_range[0] + result.phase_range[1]) / 2 - .01) < 1e-8);
  assert.equal(fitGrid([10.01, 10.115], [.001, .001], 120, 10, [4], .02).status, 'failed');
});
test('global phase is selected before greedy local subdivisions', () => {
  const result = fitPhase([10, 12].map(origin => ({targets: [origin + .001, origin + .124, origin + .251], errors: Array(3).fill(.003), bpm: 120, origin: 10})), .02);
  assert.equal(result.status, 'restored'); assert.ok(result.fits.every(f => f.split === 4)); assert.ok(Math.abs(result.phase) <= .003);
});
test('phase without supported groups fails explicitly', () => {
  const result = fitPhase([{targets: [10.137], errors: [.000001], bpm: 120, origin: 10}], 0);
  assert.equal(result.status, 'failed'); assert.equal(result.fits[0].reason, 'ambiguous_or_unsupported_song_phase');
});
