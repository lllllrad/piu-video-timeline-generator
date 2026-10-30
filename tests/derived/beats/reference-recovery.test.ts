/** A failed group cannot supply its own reference rows. */
import test from 'node:test';import assert from 'node:assert/strict';
import {coordinates,recovery,apply} from './fixtures.ts';
import {prepare} from '../../../src/piu_timeline/derived/beats/coordinates.ts';
import {recover} from '../../../src/piu_timeline/derived/beats/recovery.ts';
for(const bad of [false,true])test(`unsupported row recovery requires independent geometry: bad=${bad}`,()=>{
 const d=recovery(),n=d.notes[4];Object.assign(n,{reason:'beat_timing_reconstruction_failed',video_target_range:[1.53,1.55],beat_reconstruction:{status:'failed',reason:'no_natural_beat_subdivision',group_index:0}});
 d.notes.forEach((n,i)=>{if(i===4)return;n.beat_reconstruction={status:'restored',group_index:0};n.video_target_range=[n.target_seconds-.001,n.target_seconds+.001];});
 const groups=[{notes:d.notes.map((_,i)=>i),status:'partial',unsupported_indices:[4],unconstrained_row_domains:d.notes.map((_,i)=>i===4?[13,12]:[8+i,8+i])}];
 if(bad)n.points[0][1]+=3;const before=structuredClone(d),p=recover(d.notes,prepare(d,40,true),[[0,4,120]],0,0,0,groups,[0,0]);
 if(bad){assert.ok(!Object.hasOwn(p,4));assert.deepEqual(d,before);}else{assert.equal(n.target_seconds,1.5);assert.deepEqual(n.points,before.notes[4].points);assert.deepEqual(p[4].excluded_reference_group,[4]);assert.ok(p[4].models.every(m=>m.model.references.length>=5&&m.model.references.every(r=>r.note!==4)));assert.deepEqual(p[4].source_timing.range,[1.53,1.55]);assert.equal(p[4].source_timing.independent,false);}
});
test('unsupported and ambiguous clock rows remain distinct explicit failures',()=>{
 const targets=Array.from({length:12},(_,i)=>1+i*.125+.02),errors=targets.map(()=>.03);targets.splice(6,0,1+.625+1/12);errors.splice(6,0,.01);errors[9]=.14;
 const r=apply({notes:targets.map((target_seconds,i)=>({lane:i%3,status:'estimated',target_seconds,prediction_uncertainty_seconds:errors[i],points:[[.5,100]]}))},1);
 assert.equal(r.notes[6].beat_reconstruction.reason,'no_natural_beat_subdivision');assert.equal(r.notes[9].beat_reconstruction.reason,'ambiguous_beat_rows');assert.deepEqual(r.notes.flatMap((n,i)=>n.status==='excluded'?[i]:[]),[6,9]);
});
for(const unregistered of [false,true])test(`full application rejects an external false reference before recovery: unregistered=${unregistered}`,()=>{
 const d=coordinates(),times=d.scroll_motion.samples.map(s=>s.time),targets=Array.from({length:32},(_,i)=>1.25+i*.125);
 d.analysis_width=400;d.analysis_height=1400;d.layout={receptor_y:40/1400,lanes:Array.from({length:3},(_,i)=>({x:.1+.1*i}))};
 d.notes=targets.map((target_seconds,i)=>({lane:i%3,status:'estimated',target_seconds,prediction_uncertainty_seconds:.001,points:times.map(t=>[t,40+240*(target_seconds-t)]),motion_clock:{origin:0,velocity:240,intercept:0},motion_target_phase:240*target_seconds,timing_reconstruction:{status:'restored'}}));
 d.head_registration.notes=targets.map((_,note)=>({note,status:'registered',coordinate_method:'native_cap_measurements',observations:times.map(time=>({time}))}));
 d.scroll_motion.coordinate_registration.chunks[0].head_offsets=targets.map((t,note)=>({note,offset_pixels:40+240*t}));
 if(unregistered){d.notes.push({lane:2,status:'estimated',target_seconds:1.25,prediction_uncertainty_seconds:.001,points:times.map(t=>[t,40+240*(.9-t)]),motion_clock:{origin:0,velocity:240,intercept:0},motion_target_phase:240*.9,timing_reconstruction:{status:'restored'}});
d.head_registration.notes.push({note:32,status:'unresolved',coordinate_method:'unverified',observations:times.map(time=>({time}))});
d.scroll_motion.coordinate_registration.chunks[0].head_offsets.push({note:32,offset_pixels:40+240*.9});
}
 d.notes[12].target_seconds+=1/48;d.timing_reconstruction={status:'failed',restored_notes:d.notes.length,warnings:[{note:12,reason:'shared_motion_observation_conflict'}]};
 const before=structuredClone(d),r=apply(d,0,{},64);assert.equal(r.notes[12].target_seconds,2.75);assert.equal(r.notes[12].fit_method,'native_beat_coordinate_interpolation');
 if(unregistered){assert.equal(r.notes[0].status,'estimated');assert.ok(r.beat_timing.warnings.some(w=>w.note===32&&w.failure_detail==='incompatible_coordinate_origins'));const p=r.beat_timing.native_coordinate_recovery.find(p=>p.note===12);assert.ok(p.models.every(m=>m.model.references.every(r=>r.note!==32)));}else assert.deepEqual(r.beat_timing.warnings,[]);
 assert.deepEqual(r.timing_reconstruction.warnings,before.timing_reconstruction.warnings);assert.equal(r.timing_reconstruction.restored_notes,d.notes.length);assert.deepEqual(d,before);
});
