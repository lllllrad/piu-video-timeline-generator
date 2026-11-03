import test from 'node:test';
import assert from 'node:assert/strict';
import {summarize}from '../../../src/piu_timeline/derived/timing_summary.ts';
test('retained precision warnings do not become rejected physical timing',()=>{
 const notes=[{status:'estimated',timing_reconstruction:{status:'restored'}},
  {status:'excluded',reason:'beat_timing_reconstruction_failed',timing_reconstruction:{status:'restored'}},
  {status:'excluded',timing_reconstruction:{status:'failed'}},{status:'excluded',reason:'insufficient_track'}];
 const warnings=[{note:0,reason:'shared_subframe_clock_unresolved'},{note:0,reason:'native_motion_cadence_unresolved'},
  {note:2,reason:'shared_timing_reconstruction_failed'}],before=structuredClone({notes,warnings}),r=summarize(notes,warnings);
 assert.equal(r.failed_notes,1);assert.equal(r.restored_notes,2);assert.equal(r.warning_notes,2);assert.equal(r.warning_count,3);
 assert.equal(r.status,'failed');assert.deepEqual({notes,warnings},before);
 assert.equal(summarize([notes[0]],[warnings[0]]).failed_notes,0);
 assert.equal(summarize([notes[2]],[]).status,'failed');
});
