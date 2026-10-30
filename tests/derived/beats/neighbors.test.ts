/** Measure boundaries preserve independent references, not refuted clock rows. */
import test from 'node:test';import assert from 'node:assert/strict';
import type {RecordData} from '../../../src/piu_timeline/derived/types.ts';
import {coordinates,domain,apply} from './fixtures.ts';
import {prepare} from '../../../src/piu_timeline/derived/beats/coordinates.ts';
import {fitPhase} from '../../../src/piu_timeline/derived/beats/phase.ts';
import {spacingSupportedNotes} from '../../../src/piu_timeline/derived/beats/validation.ts';
function groups():RecordData[]{const targets=Array.from({length:8},(_,i)=>1.5+i*.125),heads=Object.fromEntries(targets.map((t,i)=>[i,{offset:500*t,lane:i%3,native_note:i,source_pts_range:[80,80.2]}]));
 return [[0,1,2,3],[4,5,6,7]].map(notes=>({notes,targets:notes.map(i=>targets[i]),errors:notes.map(i=>i===3?.13:.001),bpm:120,origin:0,native_coordinates:[{chunk:1,lane_spacing_pixels:40,heads:Object.fromEntries(notes.map((i,j)=>[j,heads[i]])),neighbor_heads:Object.fromEntries(Object.entries(heads).filter(([i])=>!notes.includes(Number(i))))}]}));}
test('neighbor-only model refutes shifted cohort without erasing the correct head',()=>{
 const targets=[...Array.from({length:6},(_,i)=>1+i*.125),.625,.75,.875,1.75,1.875,2],heads=targets.map((t,i)=>({offset:240*(t+(i>=1&&i<=5?.125:0)),lane:i%3,native_note:i}));
 const g=[[0,1,2,3,4,5],[6,7,8],[9,10,11]].map(notes=>({notes,targets:notes.map(i=>targets[i]),errors:notes.map(()=>.001),bpm:120,origin:0,...(notes[0]===0?{native_coordinates:[{chunk:0,lane_spacing_pixels:40,heads:Object.fromEntries(notes.map(i=>[i,heads[i]])),neighbor_heads:Object.fromEntries(heads.flatMap((h,i)=>notes.includes(i)?[]:[[i,h]]))}]}:{})}));
 const f=fitPhase(g,0).fits[0];assert.equal(f.status,'partial');assert.deepEqual(f.targets,[1,null,null,null,null,null]);assert.ok(f.native_coordinate_constraints.filter(p=>p.index===1).some(p=>p.model.references.map(r=>r.note).join()==='6,7,8,9,10,11'));
});
test('incompatible neighbor cannot erase an existing local coordinate constraint',()=>{
 const d=domain(),heads=prepare(d,40).chunks[0],g={notes:d.notes.map((_,i)=>i),targets:d.notes.map(n=>n.target_seconds),errors:d.notes.map(n=>n.prediction_uncertainty_seconds),bpm:120,origin:1,native_coordinates:[{chunk:0,lane_spacing_pixels:40,heads,neighbor_heads:{9:{offset:1000,lane:0,native_note:9}}}]};
 const f=fitPhase([g,{notes:[9],targets:[2.125],errors:[.001],bpm:120,origin:1}],0).fits[0];assert.equal(f.status,'restored');assert.equal(f.targets[4],1.5);
});
test('application preserves both lanes of ambiguous chord at measure boundary',()=>{
 const d=coordinates(),targets=[1.5,1.625,1.75,1.875,1.875,2,2.125,2.25,2.375];d.analysis_width=400;d.layout.lanes=Array.from({length:3},(_,i)=>({x:.1+.1*i}));
 d.notes.forEach((n,i)=>{const t=targets[i];Object.assign(n,{target_seconds:t,prediction_uncertainty_seconds:[3,4].includes(i)?.13:.001,motion_target_phase:240*t,motion_clock:{origin:0,velocity:240,intercept:0}});n.points=n.points.map(([s])=>[s,40+240*(t-s)]);d.scroll_motion.coordinate_registration.chunks[0].head_offsets[i].offset_pixels=40+240*t;});
 const before=structuredClone(d),r=apply(d);assert.equal(r.beat_timing.status,'restored');assert.deepEqual(r.notes.map(n=>n.target_seconds),targets);assert.ok(r.notes.every(n=>n.status==='estimated'));assert.deepEqual(d,before);
});
test('unique next measure rows resolve last head without changing source',()=>{
 const g=groups(),before=structuredClone(g),f=fitPhase(g,0).fits[0],refs=f.native_coordinate_constraints[0].model.references;
 assert.equal(f.status,'restored');assert.deepEqual(f.targets,[1.5,1.625,1.75,1.875]);assert.ok(!refs.some(r=>r.note===3));assert.ok(refs.some(r=>r.note>=4));assert.deepEqual(refs[0].source_pts_range,[80,80.2]);assert.deepEqual(g,before);
});
for(const kind of ['unmeasured','tempo','ambiguous','contradictory','unbracketed'])test(`unusable neighbors cannot resolve: ${kind}`,()=>{
 const g=groups();if(kind==='unmeasured')g[0].native_coordinates[0].neighbor_heads={};if(kind==='tempo')g[1].bpm=240;if(kind==='ambiguous')g[1].errors=[.51,.51,.51,.51];
 if(kind==='contradictory')g[0].native_coordinates[0].neighbor_heads[5].offset+=8;if(kind==='unbracketed'){g[0].native_coordinates[0].heads[3].offset=1250;g[0].targets[3]=2.5;}
 const f=fitPhase(g,0).fits[0];assert.notEqual(f.status,'restored');if(f.status==='partial')assert.equal(f.targets[3],null);
});
test('spatially refuted initial row cannot poison neighbor reconstruction',()=>{
 const g=groups(),targets=Array.from({length:8},(_,i)=>1.5+i*.125),times=Array.from({length:10},(_,i)=>.4+i*.02),heads=targets.map((t,i)=>({offset:40+500*t,lane:i%3,native_note:i}));
 for(const group of g)group.native_coordinates=[{chunk:0,lane_spacing_pixels:40,heads:Object.fromEntries(group.notes.map((i,j)=>[j,heads[i]])),neighbor_heads:Object.fromEntries(heads.flatMap((h,i)=>group.notes.includes(i)?[]:[[i,h]]))}];
 g[1].targets[0]+=.125;const notes=targets.map((t,i)=>({lane:i%3,status:'estimated',target_seconds:t+(i===4?.125:0),prediction_uncertainty_seconds:.001,points:times.map(s=>[s,40+500*(t-s)]),motion_clock:{origin:0,velocity:500,intercept:i===4?-62.5:0},motion_target_phase:500*t}));
 const motion={samples:times.map(time=>({time,
source_pts:80+time,
phase:500*time,
chunk:0})),
coordinate_registration:{chunks:[{chunk:0,
status:'fitted',
head_offsets:heads.map((h,
note)=>({note,
offset_pixels:h.offset}))}]}},
d:RecordData={notes,
scroll_motion:motion,
analysis_height:1600,
layout:{receptor_y:40/1600},
head_registration:{notes:notes.map((_,
note)=>({note,
status:'registered',
coordinate_method:'native_cap_measurements',
observations:times.map(time=>({time}))}))}},
s=prepare(d,
40),
before=structuredClone({d,
g});


 const r=fitPhase(g,0,f=>spacingSupportedNotes(d.notes,g,f,40,motion,s));assert.deepEqual(r.fits[0].targets,targets.slice(0,4));assert.deepEqual(r.fits[1].targets,[null,...targets.slice(5)]);assert.deepEqual(r.consistent_notes,[0,1,2,3,5,6,7]);
 assert.ok((r.fits[0].native_coordinate_constraints??[]).every(p=>p.model.references.every(r=>r.note!==4)));assert.deepEqual({d,g},before);
});
