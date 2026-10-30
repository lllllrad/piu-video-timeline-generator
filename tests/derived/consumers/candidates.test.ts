import test from 'node:test';import assert from 'node:assert/strict';
import {candidates} from '../../../src/piu_timeline/derived/candidates.ts';
import {recoverRows} from '../../../src/piu_timeline/derived/recovery.ts';
import {receptorRuns} from '../../../src/piu_timeline/derived/hold_state.ts';
import {note,event,run} from './fixtures.ts';
import type {RecordData} from '../../../src/piu_timeline/derived/types.ts';
const owned=(target=10)=>({notes:[note(10),note(target,1)],matches:[{note:0,target_seconds:10,combo_event:0,combo_lower_seconds:10,combo_upper_seconds:10.02}]});
test('owned refresh cannot also be a later row or duplicate word vote',()=>{const [r,j]=candidates(owned(10.08),[event(),event(10.01,10.03,'judgment')]);assert.ok(!r[1]);assert.ok(j[1].includes('refresh_already_assigned_to_another_row'));});
test('owned chord can include a separately supported other lane',()=>{const d={...owned(10.005),hold_analysis:{receptor_runs:[run(1,false,9,9.98),run(1,true,10,10.1,9.98)]}},[r]=candidates(d,[event()]);assert.equal(r[1].length,1);assert.ok(r[1][0].lane_receptor_support);});
test('adjacent lane flash does not support an inactive lane',()=>{const [r,j]=candidates({notes:[note(10),note(10,1)],hold_analysis:{receptor_runs:[run(0,false,9,9.98),run(0,true,10,10.1,9.98),run(1,true,8,8.2,7.9),run(1,false,8.2,11)]}},[event()]);assert.ok(r[0]);assert.ok(!r[1]);assert.ok(j[1].includes('receptor_lane_not_active'));});
test('obscured receptor remains unknown and cannot establish recovered input',()=>{
 const d={notes:[note(10)],hold_analysis:{receptor_runs:[run(0,true,8,8.2,7.9),run(0,false,9,9.98),run(0,null,10,10.04),run(0,false,10.06,11)]}},[r,j]=candidates(d,[event()]);
 assert.ok(r[0]);assert.equal(r[0][0].lane_receptor_support,false);assert.equal(r[0][0].lane_receptor_status,'unknown');assert.ok(!(j[0]??[]).includes('receptor_lane_not_active'));assert.deepEqual(recoverRows({...d,combo_events:[event()]}),[[],[]]);
 Object.assign(d.hold_analysis.receptor_runs[2],{start_seconds:10.1,end_seconds:10.2});const [a,b]=candidates(d,[event()]);assert.ok(!a[0]);assert.ok(b[0].includes('receptor_lane_not_active'));
});
test('nearby before/after rows cannot all share a better-supported candidate',()=>{const [r,j]=candidates({notes:[note(9.9),note(10),note(10.1)]},[event()]);assert.deepEqual(Object.keys(r),['1']);for(const i of [0,2])assert.ok(j[i].includes('another_note_row_is_better_supported'));});
test('hold tick requires a separate lane onset for tap',()=>{
 const d={notes:[note(10.5,1)],hold_analysis:{holds:[{start_range:[10,10.01],start_censored:false,end_range:[11,11.01]}],receptor_runs:[run(1,false,9,9.98),run(1,true,10,10.8,9.98)]}},[r,j]=candidates(d,[event(10.5,10.52,'counter_frames')]);assert.deepEqual(r,{});assert.ok(j[0].includes('hold_tick_without_independent_lane_onset'));
 d.hold_analysis.receptor_runs[1]=run(1,true,10.49,10.8,10.48);assert.ok(candidates(d,[event(10.5,10.52,'counter_frames')])[0][0]);
});
test('a real frame-bracket tie retains explicit alternative rows',()=>{const [r]=candidates({notes:[note(9.995),note(10.025)]},[event()]);assert.deepEqual(Object.keys(r),['0','1']);assert.ok(Object.values(r).every(e=>e[0].alternative_rows===2));});
test('tap refresh during flash uses the bracket before lane light becomes visible',()=>{
 const frames=[[10,false],[10.02,false],[10.04,null],[10.06,null],[10.08,true],[10.1,true]].map(([t,lit])=>({playback_seconds:Number(t),source_pts_seconds:Number(t)+100,receptor_lit:[lit],common_receptor_flash:lit===null})),d={notes:[note(10.05)],matches:[],hold_analysis:{holds:[{start_range:[9,9.01],start_censored:false,end_range:[11,11.01]}],receptor_runs:receptorRuns(frames)}};
 const [r]=candidates(d,[event(10.04,10.05)]);assert.ok(r[0]);assert.deepEqual(r[0][0].candidate_range,[10.04,10.05]);assert.deepEqual(r[0][0].lane_support_runs[0].onset_range,[10.02,10.08]);assert.deepEqual(d.matches,[]);
 frames[0].receptor_lit=[true];frames[1].receptor_lit=[true];d.hold_analysis.receptor_runs=receptorRuns(frames);assert.ok(!candidates(d,[event(10.04,10.05)])[0][0]);
});
test('processed order rejects earlier note after later anchor',()=>{const [r,j]=candidates({notes:[note(10.1),note(9.99,1),note(10.15,1)],matches:[{note:0,target_seconds:10.1,combo_event:1,combo_lower_seconds:10.1,combo_upper_seconds:10.12}]},[event(10.15,10.17)]);assert.ok(!r[1]);assert.ok(j[1].includes('violates_processed_row_order'));assert.ok(r[2]);});
test('narrow word refresh does not fan out over aggregate counter rows',()=>{const [r]=candidates({notes:[note(9.9),note(10)]},[{...event(9.89,10.02),delta:2},event(10,10.02,'judgment')]);assert.deepEqual(r[0].map(e=>e.source),['combo']);assert.deepEqual(new Set(r[1].map(e=>e.source)),new Set(['combo','judgment']));});
for(const [lo,hi,want] of [[9.75,9.75,true],[10.5,10.5,true],[9.74,9.749,false],[10.501,10.51,false],[10.4,10.42,true]])test(`hard candidate window includes only valid boundary ${lo}`,()=>assert.equal(!!candidates({notes:[note(10)]},[event(Number(lo),Number(hi))])[0][0],want));
test('wide bracket is intersected while preserving source evidence',()=>{const e={...event(9,11),source_pts_seconds:[109,111]},[r]=candidates({notes:[note(10)]},[e]),p=r[0][0];assert.deepEqual(p.candidate_range,[9.75,10.5]);assert.deepEqual([p.lower_seconds,p.upper_seconds],[9,11]);assert.deepEqual(p.source_pts_seconds,[109,111]);assert.ok(!Object.hasOwn(e,'candidate_range'));});
test('uncertainty or local context cannot expand hard time limits',()=>{
 assert.deepEqual(candidates({notes:[{...note(10),prediction_uncertainty_seconds:5}]},[event(10.51,10.52)])[0],{});
 const d={notes:[note(9.9,1),note(10)],matches:[{note:0,target_seconds:9.9,combo_event:1,combo_lower_seconds:10.7,combo_upper_seconds:10.72}]};assert.ok(!candidates(d,[event(10.8,10.82)])[0][1]);
});
test('outside word cannot ride inside a wide counter family',()=>{const [r]=candidates({notes:[note(10)]},[{...event(9,10.7),delta:2},event(10.68,10.7,'judgment')]);assert.deepEqual(r[0].map(e=>e.source),['combo']);assert.deepEqual(r[0][0].candidate_range,[9.75,10.5]);});
