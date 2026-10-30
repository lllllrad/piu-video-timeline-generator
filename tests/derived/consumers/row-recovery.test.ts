import test from 'node:test';import assert from 'node:assert/strict';
import {recoverRows} from '../../../src/piu_timeline/derived/recovery.ts';
import {row} from './fixtures.ts';
test('other press offsets do not move independent onset eligibility',()=>{
 const d=row();d.notes.push({...d.notes[0],target_seconds:1.5,lane:1});d.matches=[{note:1,target_seconds:1.5,combo_event:1,observation_lower_seconds:1.9,observation_upper_seconds:1.92}];
 const [m,r]=recoverRows(d);assert.deepEqual(r,[0]);assert.equal(m.find(m=>m.note===0).observation_upper_seconds,1.04);
 const a=structuredClone(d);a.notes.push({...d.notes[0],target_seconds:.6});assert.deepEqual(recoverRows(a)[1],[]);d.display_delay_correction_ms=400;assert.deepEqual(recoverRows(d)[1],[]);
});
test('flash-corroborated onset survives candidate lane gate',()=>{const d=row();Object.assign(d.hold_analysis.receptor_runs[1],{frames:1,end_seconds:1.02,corroborating_lit_frames_after_flash:1,corroborating_source_pts_seconds:11.1,corroborating_playback_seconds:1.1});assert.deepEqual(recoverRows(d)[1],[0]);});
test('unique row uses its own lane and original bracket without changing input',()=>{
 const d=row(),before=structuredClone(d),[m,r]=recoverRows(d);assert.deepEqual(d,before);assert.deepEqual(r,[0]);assert.equal(m[0].observation_lower_seconds,1.02);assert.equal(m[0].observation_upper_seconds,1.04);assert.equal(m[0].judgment_label,'GREAT');assert.deepEqual(m[0].lane_onset_source_pts_seconds,[11,11.02]);assert.equal(m[0].combo_event,0);
});
test('repeated same-lane rows cannot claim one onset even after one is assigned',()=>{
 const d=row();d.notes.push({...d.notes[0],target_seconds:1.035});assert.deepEqual(recoverRows(d)[1],[]);d.matches=[{note:1,target_seconds:1.035,combo_event:0,observation_lower_seconds:1.02,observation_upper_seconds:1.04}];assert.deepEqual(recoverRows(d)[1],[]);
});
test('chord shares one row but requires both independent lane onsets',()=>{
 const d=row();d.notes.push({...d.notes[0],lane:1});d.hold_analysis.receptor_runs.push(...d.hold_analysis.receptor_runs.map(r=>({...r,lane:1})));const [m,r]=recoverRows(d);assert.deepEqual(new Set(r),new Set([0,1]));assert.ok(m.every(m=>m.row_note_count===2));d.hold_analysis.receptor_runs=d.hold_analysis.receptor_runs.slice(0,2);assert.deepEqual(recoverRows(d)[1],[0]);
});
for(const kind of ['static','single','missing','miss','gap','hold','distant'])test(`unproven lane onset remains unresolved: ${kind}`,()=>{
 const d=row(),r=d.hold_analysis.receptor_runs[1];if(kind==='static')r.onset_range=null;if(kind==='single')r.frames=1;if(kind==='missing')r.lane=1;
 if(kind==='miss'){d.combo_events=[];d.judgment_events[0].label='MISS';}if(kind==='gap'){d.combo_events[0].lower_seconds=.5;d.judgment_events[0].lower_seconds=.5;}if(kind==='hold')d.notes[0].note_type='hold';if(kind==='distant')d.notes[0].target_seconds=.5;assert.deepEqual(recoverRows(d)[1],[]);
});
test('conflicting display alternatives remain unresolved',()=>{const d=row();d.combo_events.push({delta:1,lower_seconds:1.055,upper_seconds:1.065});assert.deepEqual(recoverRows(d)[1],[]);});
test('distant review candidate cannot veto strictly timed refresh without local corroboration',()=>{
 const d=row(),before=structuredClone(d);d.hold_analysis.receptor_runs[1].end_seconds=1.3;d.combo_events.push({delta:1,lower_seconds:1.18,upper_seconds:1.2});const [m,r]=recoverRows(d);assert.deepEqual(r,[0]);assert.equal(m[0].combo_event,0);assert.equal(m[0].observation_upper_seconds,1.04);assert.deepEqual(d.notes,before.notes);
 d.notes.push({...d.notes[0],target_seconds:1.5,lane:1});d.matches=[{note:1,target_seconds:1.5,combo_event:2,observation_lower_seconds:1.68,observation_upper_seconds:1.7}];assert.deepEqual(recoverRows(d)[1],[]);
});
