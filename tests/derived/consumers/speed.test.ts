import test from 'node:test';import assert from 'node:assert/strict';
import {estimate} from '../../../src/piu_timeline/derived/speed.ts';
import {contracts} from '../../../src/piu_timeline/derived/contracts.ts';
import type {RecordData} from '../../../src/piu_timeline/derived/types.ts';
function scene(ratio=2,repeated=false):RecordData{return {analysis_width:400,layout:{lanes:[{x:.2},{x:.3}]},scroll_motion:{format:{method:'registered_peer_displacement'},coordinate_registration:{format:contracts.registration},samples:Array.from({length:300},(_,i)=>{const t=i/60,r=repeated?Math.floor(i/2)*2/60:t;return {time:1000+t,source_pts:9000+t,phase:240*Math.min(r,2)+240*ratio*Math.max(0,r-2),chunk:0,support:4,lanes:2};})}};}
for(const ratio of [.5,1.73,2])test(`native speed transition retains real ratio and original frame brackets: ${ratio}`,()=>{
 const d=scene(ratio),before=structuredClone(d),r=estimate(d);assert.ok(r.transitions.length);const c=r.transitions.reduce((a,b)=>Math.abs(a.estimated_transition_seconds-1002)<Math.abs(b.estimated_transition_seconds-1002)?a:b);
 assert.ok(Math.abs(c.speed_multiplier-ratio)<=.02);assert.ok(c.speed_ratio_range[0]<=ratio&&c.speed_ratio_range[1]>=ratio);assert.ok(Math.abs(c.estimated_transition_seconds-1002)<=.02);assert.equal(c.auto_recordable,true);
 for(const side of ['before','after'])assert.ok(Math.abs(c[side].source_pts_seconds[0]-c[side].start-8000)<1e-7);assert.deepEqual(d,before);
});
test('duplicate rendered frames do not create speed changes',()=>{
 assert.deepEqual(estimate(scene(1,true)).transitions,[]);const r=estimate(scene(2,true));assert.ok(r.transitions.length);assert.ok(r.transitions.some(c=>c.speed_ratio_range[0]<=2&&2<=c.speed_ratio_range[1]));
});
test('missing independent support, capture gap or unregistered motion cannot establish transition',()=>{
 let d=scene();d.scroll_motion.samples.forEach(s=>Object.assign(s,{support:1,lanes:1}));assert.deepEqual(estimate(d).transitions,[]);
 d=scene();d.scroll_motion.samples.forEach(s=>{if(s.time>=1002)s.chunk=1;});assert.deepEqual(estimate(d).transitions,[]);d.scroll_motion.format.method='unregistered_correspondence';assert.equal(estimate(d).status,'unavailable');
});
test('local capture distortion remains reviewable instead of authorizing metadata',()=>{
 const d=scene(1);d.scroll_motion.samples.forEach(s=>{const dt=s.time-1002;if(Math.abs(dt)<.5)s.phase+=15*Math.cos(dt*Math.PI)**2;});const r=estimate(d).transitions;
 assert.ok(r.length);assert.ok(r.some(c=>c.review_reasons.includes('longer_native_flanks_do_not_confirm_change')));assert.ok(!r.some(c=>c.auto_recordable));
});
test('unregistered integrated coordinates remain proposals requiring review',()=>{
 const d=scene();delete d.scroll_motion.coordinate_registration;const r=estimate(d).transitions;assert.ok(r.length);assert.ok(!r.some(c=>c.auto_recordable));assert.ok(r.every(c=>c.review_reasons.includes('joint_native_coordinate_registration_required')));
});
