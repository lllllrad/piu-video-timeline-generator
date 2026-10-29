import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeScene, template} from '../fixtures.ts';
import {contracts} from '../../../src/piu_timeline/derived/contracts.ts';
import {reconstruct} from '../../../src/piu_timeline/derived/beats/stage.ts';
import {prepare} from '../../../src/piu_timeline/derived/beats/coordinates.ts';
import {spacingFailures} from '../../../src/piu_timeline/derived/beats/spacing.ts';
import {text} from '../../../src/piu_timeline/derived/charts/ucs.ts';

function scene(spacing:number, fps:number, certifiedTail=false){
 const events:[number,number][]=[[1,0],[1.125,1],[1.125,2],[1.25,3],[1.375,4],[1.5,0],[1.625,1],[1.75,2]];
 const d=nativeScene(events,spacing,fps,5,{end:2});
 d.notes[0].motion_target_phase-=.2*spacing;
 d.notes[0].points=d.notes[0].points.map(([t,y])=>[t,y-.2*spacing]);
 d.scroll_motion.coordinate_registration.chunks[0].head_offsets[0].offset_pixels-=.2*spacing;
 d.head_registration={format:{native_cap_registration:structuredClone(contracts.native_anchor)},notes:d.notes.map((n,i)=>({
  note:i,coordinate_method:'native_image_anchors',coordinate_status:i===0&&!certifiedTail?'unregistered':'registered',
  observations:n.points.map(([time,y])=>({time,source_pts_seconds:80+time,native_y_pixels:y,template:`cap-${i}`,
   cap_reference_sha256:`reference-${i}`, ...(i>0||certifiedTail?{
    native_cap_coordinate_uncertainty_pixels:spacing/80,native_cap_reference_scale_y:spacing/80}: {})}))}))};
 return d;
}
for(const spacing of[20,40,80])for(const fps of[30,60,120])test(`unregistered tail cannot veto a certified chord: spacing=${spacing}, fps=${fps}`,()=>{
 const d=scene(spacing,fps),before=structuredClone(d);
 const r=reconstruct({schema:1,data:d,reference:{status:'available',song_start_seconds:0,alignment_uncertainty_seconds:0},timing_text:text(template(4,64))});
 for(const i of[1,2]){
  assert.equal(r.notes[i].status,'estimated',JSON.stringify(r.beat_timing.warnings));
  assert.ok(Math.abs(r.notes[i].target_seconds-1.125)<1e-8);
 }
 assert.ok(r.beat_timing.warnings.some(w=>w.note===0),'unsupported coordinate remains a warning');
 assert.equal(r.beat_timing.status,'failed');
 const support=prepare(d,spacing);
 assert.ok(!Object.hasOwn(support.chunks[0],0),'an unknown origin cannot anchor an independent model');
 assert.deepEqual(d,before);
 const changed=structuredClone(d);changed.combo_events=[{time:.3,value:999}];changed.matches=[{note:1,input_seconds:1.2}];
 assert.deepEqual(reconstruct({schema:1,data:changed,reference:{status:'available',song_start_seconds:0,alignment_uncertainty_seconds:0},timing_text:text(template(4,64))}),r);
});

test('a certified geometric contradiction still fails ordinary spacing checks',()=>{
 const d=scene(40,60,true),failures=spacingFailures(d.notes,40,d.scroll_motion,prepare(d,40));
 assert.ok(failures.some(w=>w.note===0),'a measured wrong offset is not treated as an unknown origin');
});

test('uncalibrated origins cancel only for the same image reference',()=>{
 const d=scene(40,60),a=d.head_registration.notes[0],b=d.head_registration.notes[1];
 for(const o of b.observations){delete o.native_cap_coordinate_uncertainty_pixels;delete o.native_cap_reference_scale_y;o.cap_reference_sha256='reference-0';}
 const support=prepare(d,40),failures=spacingFailures(d.notes,40,d.scroll_motion,support);
 assert.ok(failures.some(w=>w.peer_notes.includes(0)&&w.peer_notes.includes(1)&&w.failure_detail!=='incompatible_coordinate_origins'),
  'one shared matching origin remains eligible for an ordinary strict spacing check');
 for(const o of a.observations)o.cap_reference_sha256='different-reference';
 const incompatible=spacingFailures(d.notes,40,d.scroll_motion,prepare(d,40));
 assert.ok([0,1].every(i=>incompatible.some(w=>w.note===i&&w.failure_detail==='incompatible_coordinate_origins')));
});

test('one explicitly bounded projection conflict does not change the trajectory convention',()=>{
 const d=scene(40,60),r=d.head_registration.notes[1],o=r.observations[5];
 r.coordinate_status='projected';o.native_cap_registration_status='conflicting';
 o.native_cap_projection_uncertainty_pixels=1.5;o.native_cap_reference_template=o.template;
 delete o.native_cap_coordinate_uncertainty_pixels;
 const support=prepare(d,40);
 assert.ok(support.chunks[0][1]);
 assert.ok(!support.observed[1].includes(o.time),'the conflict itself cannot supply an independent coordinate');
 const result=reconstruct({schema:1,data:d,reference:{status:'available',song_start_seconds:0,alignment_uncertainty_seconds:0},timing_text:text(template(4,64))});
 assert.ok([1,2].every(i=>result.notes[i].status==='estimated'&&Math.abs(result.notes[i].target_seconds-1.125)<1e-8));
 assert.equal(d.head_registration.notes[1].observations[5].native_cap_registration_status,'conflicting');
 delete o.native_cap_projection_uncertainty_pixels;
 assert.ok(!prepare(d,40).chunks[0][1],'an unsupported conflict cannot claim the projected convention');
});

test('a scene containing only unsupported origins still reports coordinate failures',()=>{
 const d=scene(40,60);
 for(const r of d.head_registration.notes)for(const o of r.observations){delete o.native_cap_coordinate_uncertainty_pixels;delete o.native_cap_reference_scale_y;}
 const support=prepare(d,40);
 assert.ok(support,'missing calibrated references must not disable pair diagnostics');
 assert.ok(spacingFailures(d.notes,40,d.scroll_motion,support).some(w=>w.failure_detail==='incompatible_coordinate_origins'));
});

test('an intervening unregistered origin cannot hide a certified spacing contradiction',()=>{
 const d=scene(40,60,true);
 d.notes=d.notes.slice(0,3);d.head_registration.notes=d.head_registration.notes.slice(0,3);
 d.scroll_motion.coordinate_registration.chunks[0].head_offsets=d.scroll_motion.coordinate_registration.chunks[0].head_offsets.slice(0,3);
 const middle=d.notes[1],record=d.head_registration.notes[1];
 middle.points=middle.points.map(([t,y])=>[t,y-4]);
 for(const o of record.observations){o.native_y_pixels-=4;delete o.native_cap_coordinate_uncertainty_pixels;delete o.native_cap_reference_scale_y;}
 const failures=spacingFailures(d.notes,40,d.scroll_motion,prepare(d,40));
 assert.ok(failures.some(w=>w.peer_notes[0]===0&&w.peer_notes[1]===2&&w.failure_detail!=='incompatible_coordinate_origins'));
});
