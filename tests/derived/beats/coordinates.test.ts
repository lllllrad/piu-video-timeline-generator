import test from 'node:test';import assert from 'node:assert/strict';
import {prepare,predictions,fit} from '../../../src/piu_timeline/derived/beats/coordinates.ts';
import {spacingFailures,attributedHeads} from '../../../src/piu_timeline/derived/beats/spacing.ts';
import {prepare as chords} from '../../../src/piu_timeline/derived/beats/chords.ts';
import {coordinates,chord,resize,near} from './fixtures.ts';

test('per-frame native centers do not require a constant outline offset',()=>{
 const d=coordinates();d.head_registration.notes.forEach(r=>r.status='unresolved');
 assert.deepEqual(spacingFailures(d.notes,40,d.scroll_motion,prepare(d,40)),[]);
 d.notes[4].points[0][1]+=3;assert.deepEqual(predictions(4,5,d.notes,[.5,.68],prepare(d,40)),[]);
});
test('independent coordinates validate pixel spacing despite local clock bias',()=>{
 const d=coordinates(),before=structuredClone(d),checks=[];
 assert.ok(spacingFailures(d.notes,40,d.scroll_motion).some(w=>w.peer_notes.join() ==='4,5'));
 const support=prepare(d,40),frozen=structuredClone(support);
 assert.deepEqual(spacingFailures(d.notes,40,d.scroll_motion,support,checks),[]);
 const proof=checks.find(c=>c.peer_notes.join()==='4,5').models[0];
 assert.ok(near(proof.predicted_gap_pixels,30));assert.ok(near(proof.velocity_pixels_per_second,240));
 assert.deepEqual(proof.references.map(r=>r.note),[0,1,2,3,6,7,8]);assert.deepEqual(proof.references[0].source_pts_range,[80.5,80.68]);
 assert.deepEqual(d,before);assert.deepEqual(support,frozen);
});
test('an independently refuted row keeps its original coordinate proof',()=>{
 const d=coordinates(),support=prepare(d,40);d.notes[4].target_seconds+=.06;
 const pair=spacingFailures(d.notes,40,d.scroll_motion,support).find(w=>w.peer_notes.join()==='4,5');
 assert.ok(pair.independent_coordinate_models);assert.ok(Math.abs(pair.observed_gap_pixels-pair.reconstructed_gap_pixels)>pair.tolerance_pixels);
});
for(const kind of['outlier','unverified','short','failed_block'])test(`unsupported native anchors cannot supply a coordinate model: ${kind}`,()=>{
 const d=coordinates();if(kind==='outlier')d.notes[4].points[0][1]+=3;
 if(kind==='unverified')Object.assign(d.head_registration.notes[4],{status:'unresolved',coordinate_method:'unverified'});
 if(kind==='short')d.head_registration.notes[4].observations=d.head_registration.notes[4].observations.slice(0,3);
 if(kind==='failed_block')d.scroll_motion.coordinate_registration.chunks[0].status='failed';
 assert.deepEqual(predictions(4,5,d.notes,[.5,.68],prepare(d,40)),[]);
});
test('coordinate models never extrapolate or train on the tested pair',()=>{
 const d=coordinates(),s=prepare(d,40);
 assert.deepEqual(predictions(0,1,d.notes,[.5,.68],s),[]);assert.deepEqual(predictions(4,5,d.notes,[.51,.55],s),[]);
 s.chunks[0]=Object.fromEntries(Object.entries(s.chunks[0]).filter(([i])=>[0,2,4,5,6,8].includes(Number(i))));
 assert.deepEqual(predictions(4,5,d.notes,[.5,.68],s),[]);
});
test('every reference must fit without dropping a speed transition',()=>{
 const d=coordinates(),s=prepare(d,40),refs=Object.entries(s.chunks[0]).filter(([i])=>![4,5].includes(Number(i))).map(([i,h])=>({note:Number(i),target_seconds:d.notes[i].target_seconds,...h}));
 assert.ok(fit(refs,40));for(const kind of['bad_row','speed_change','one_lane','one_time']){
  const r=structuredClone(refs);if(kind==='bad_row')r[2].target_seconds+=.08;
  if(kind==='speed_change')r.forEach(h=>h.offset+=Math.max(0,h.target_seconds-1.4)*60);
  if(kind==='one_lane')r.forEach(h=>h.lane=0);if(kind==='one_time')r.forEach(h=>h.target_seconds=1);
  assert.equal(fit(r,40),null,kind);
 }
});
test('conflicting source positions cannot count as independent pair support',()=>{
 const d=coordinates(),r=d.head_registration.notes[4];r.observations[0].native_cap_registration_status='conflicting';
 assert.ok(predictions(4,5,d.notes,[.5,.68],prepare(d,40)).every(m=>m.coobserved_points===9));
 r.observations.forEach(s=>s.native_cap_registration_status='conflicting');assert.deepEqual(predictions(4,5,d.notes,[.5,.68],prepare(d,40)),[]);
});
for(const scale of[.5,1,2,4])test(`coordinate qualification preserves decisions after storage and scaling: ${scale}`,()=>{
 for(const [error,accepted]of[[1.2,true],[1.8,false]]as const){const d=coordinates();d.notes[4].points[0][1]+=error;assert.equal(Object.hasOwn(prepare(resize(d,scale),40*scale).chunks[0],4),accepted);}
 for(const [error,accepted]of[[.8,true],[1.2,true],[2.4,false]]as const){const d=coordinates();d.notes[0].points.forEach(p=>p[1]+=error);d.scroll_motion.coordinate_registration.chunks[0].head_offsets[0].offset_pixels+=error;const r=resize(d,scale);assert.equal(!!predictions(4,5,r.notes,[.5,.68],prepare(r,40*scale)).length,accepted);}
 for(const wrong of[false,true]){const d=coordinates();if(wrong)d.notes[4].target_seconds+=.012;const r=resize(d,scale);assert.equal(spacingFailures(r.notes,40*scale,r.scroll_motion,prepare(r,40*scale)).some(w=>w.note===4),wrong);}
 const d=chord();d.notes[1].points.forEach(p=>p[1]+=.6);assert.deepEqual(chords(resize(d,scale),40*scale).map(p=>p.peer_notes),[[0,1]]);
});
test('one wrong row rejects only its own coordinate, preserving the verified neighbor',()=>{
 const d=coordinates();d.notes[4].target_seconds+=.06;const before=structuredClone(d),failures=spacingFailures(d.notes,40,d.scroll_motion,prepare(d,40));
 assert.deepEqual([...new Set(failures.map(w=>w.note))],[4]);const pair=failures.find(w=>w.peer_notes.join()==='4,5'),proof=pair.native_position_attribution[0];
 assert.deepEqual(proof.contradicting_notes,[4]);assert.ok(Math.abs(proof.peer_position_errors_pixels[0])>proof.maximum_position_error_pixels);
 assert.ok(Math.abs(proof.peer_position_errors_pixels[1])<=proof.maximum_position_error_pixels);
 assert.ok(pair.independent_coordinate_models[0].references.every(r=>![4,5].includes(r.note)));assert.deepEqual(d,before);
});
test('unattributed or contradictory models keep both peers unresolved',()=>{
 const notes=[{target_seconds:0},{target_seconds:1}]as any;
 const model=(offsets,chunk=0)=>({chunk,lane_spacing_pixels:40,peer_offsets_pixels:offsets,maximum_reference_error_pixels:0,coordinate_domain:{vertices:[[10,0]],maximum_reference_error_pixels:0},offset_at_origin_pixels:0,origin_seconds:0,velocity_pixels_per_second:10});
 for(const models of[[],[model([0,13]),model([3,10],1)],[{}]])assert.deepEqual(attributedHeads(0,1,notes,models)[0],[0,1]);
 const [rejected,proof]=attributedHeads(0,1,notes,[model([.75,9.25])]);assert.deepEqual(rejected,[]);assert.equal(proof[0].maximum_position_error_pixels,1);
 const d=coordinates();d.notes[4].target_seconds+=.06;assert.deepEqual(spacingFailures(d.notes,40,d.scroll_motion).filter(w=>w.peer_notes.join()==='4,5').map(w=>w.note),[4,5]);
});
