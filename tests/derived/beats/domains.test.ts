/** Independent registered geometry constrains uncertain rows without nearest-row guessing. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {domain,apply,chord,spatial} from './fixtures.ts';
import {prepare} from '../../../src/piu_timeline/derived/beats/coordinates.ts';
import {fitGrid} from '../../../src/piu_timeline/derived/beats/grid.ts';
import {fitPhase} from '../../../src/piu_timeline/derived/beats/phase.ts';
import {spacingSupportedNotes as spacingSupported} from '../../../src/piu_timeline/derived/beats/validation.ts';
const blocks=data=>{const s=prepare(data,40);return Object.entries(s.chunks).map(([chunk,heads])=>({chunk:Number(chunk),heads,lane_spacing_pixels:s.lane_spacing_pixels}));};
const fit=(data,splits?)=>fitGrid(data.notes.map(n=>n.target_seconds),data.notes.map(n=>n.prediction_uncertainty_seconds),120,1,splits,0,[],blocks(data));
test('registered positions narrow broad time domains and preserve native provenance',()=>{
 const data=domain(),before=structuredClone(data),r=apply(data,1),g=r.beat_timing.groups[0],p=g.native_coordinate_constraints.find(p=>p.index===4);
 assert.equal(r.beat_timing.status,'restored');assert.ok(r.notes.every(n=>n.status==='estimated'));assert.equal(g.split,4);
 assert.deepEqual(p.original_domain,[3,5]);assert.deepEqual(p.allowed_domain,[4,4]);assert.ok(!p.model.references.some(r=>r.note===4));
 assert.deepEqual(p.model.references[0].source_pts_range,[80.5,80.68]);assert.deepEqual(r.notes[4].video_target_range,[1.37,1.63]);assert.deepEqual(data,before);
});
for(const kind of ['few','unmeasured','bad','extrapolation','fine'])test(`unproven row remains partial: ${kind}`,()=>{
 const d=domain();
 if(kind==='few')d.head_registration.notes.slice(5).forEach(r=>Object.assign(r,{status:'unresolved',coordinate_method:'unverified'}));
 if(kind==='unmeasured')Object.assign(d.head_registration.notes[4],{status:'unresolved',coordinate_method:'unverified'});
 if(kind==='bad'){d.notes[2].points.forEach(p=>p[1]+=12);d.scroll_motion.coordinate_registration.chunks[0].head_offsets[2].offset_pixels+=12;}
 if(kind==='extrapolation'){d.notes[4].prediction_uncertainty_seconds=.001;d.notes[0].prediction_uncertainty_seconds=.13;}
 const r=fit(d,kind==='fine'?[192]:undefined),index=kind==='extrapolation'?0:4;
 assert.equal(r.status,'partial');assert.equal(r.targets[index],null);
 if(kind==='bad'){assert.equal(r.reason,'native_coordinate_domains_incompatible');assert.equal(r.targets[2],null);}else{assert.equal(r.reason,'ambiguous_beat_rows');assert.equal(r.rows[index],null);}
});
for(const narrow of [false,true])test(`independent geometry refutes coarse or unique clock row: narrow=${narrow}`,()=>{
 const d=domain();if(narrow)d.notes[4].prediction_uncertainty_seconds=.001;
 d.notes[4].points.forEach(p=>p[1]+=15);d.scroll_motion.coordinate_registration.chunks[0].head_offsets[4].offset_pixels+=15;
 const r=fit(d);assert.equal(r.status,narrow?'partial':'restored');
 if(narrow){assert.equal(r.reason,'native_coordinate_domains_incompatible');assert.equal(r.targets[4],null);assert.ok(r.targets.every((t,i)=>i===4||t!==null));}
 else{assert.equal(r.split,8);assert.equal(r.targets[4],1.5625);}
});
test('unsupported row cannot force unique neighbors onto an ambiguous finer grid',()=>{
 const targets=Array.from({length:12},(_,i)=>1+i*.125+.02),errors=targets.map(()=>.03);targets.splice(6,0,1+.625+1/12);errors.splice(6,0,.01);
 const r=fitGrid(targets,errors,120,1);assert.equal(r.status,'partial');assert.equal(r.split,4);assert.deepEqual(r.unresolved_indices,[6]);assert.equal(r.targets[6],null);
 assert.deepEqual(r.targets.filter(t=>t!==null),Array.from({length:12},(_,i)=>1+i*.125));assert.ok(r.row_domains[6][0]>r.row_domains[6][1]);assert.equal(r.reason,'no_natural_beat_subdivision');
});
test('common phase preserves independent rows without choosing an ambiguous neighbor',()=>{
 const group={targets:[10,10.125,10.25,10.375],errors:[.001,.001,.14,.001],bpm:120,origin:10},before=structuredClone(group),r=fitPhase([group],.002),f=r.fits[0];
 assert.equal(r.status,'restored');assert.equal(f.status,'partial');assert.equal(f.split,4);assert.deepEqual(f.rows.map(v=>v===0?0:v),[0,1,null,3]);assert.deepEqual(f.targets,[10,10.125,null,10.375]);assert.deepEqual(f.unresolved_indices,[2]);assert.deepEqual(group,before);
});
test('application warns on ambiguous head and preserves unique neighboring rows',()=>{
 const d=domain();Object.assign(d.head_registration.notes[4],{status:'unresolved',coordinate_method:'unverified'});const before=structuredClone(d),r=apply(d,1),n=r.notes[4];
 assert.equal(r.beat_timing.status,'failed');assert.equal(r.beat_timing.groups[0].status,'partial');assert.deepEqual(new Set(r.beat_timing.warnings.map(w=>w.note)),new Set([4]));
 assert.equal(n.status,'excluded');assert.equal(n.reason,'beat_timing_reconstruction_failed');assert.equal(n.target_seconds,null);assert.deepEqual(n.video_target_range,[1.37,1.63]);assert.equal(n.beat_reconstruction.reason,'ambiguous_beat_rows');
 assert.ok(r.notes.every((n,i)=>n.beat_reconstruction.group_index===0&&(i===4||n.status==='estimated'&&n.beat_reconstruction.status==='restored')));assert.deepEqual(d,before);
});
test('partial assignment cannot bypass independent spatial rejection',()=>{
 const {notes,motion}=spatial();notes.push({status:'estimated',lane:2,target_seconds:1.25,points:[]});
 const g={notes:[0,2,1],targets:[1.007,1.25,1.507],errors:[.01,.26,.01],bpm:120,origin:0},f=fitGrid(g.targets,g.errors,120,0);
 assert.equal(f.status,'partial');assert.deepEqual(spacingSupported(notes,[g],[f],40,motion),[0,1]);motion.coordinate_registration.chunks[0].head_offsets[1].offset_pixels+=6;assert.deepEqual(spacingSupported(notes,[g],[f],40,motion),[]);
});
test('different supported identities cannot select a common phase',()=>{
 const r=fitPhase([{targets:[1,1.25],errors:[.02,.3],bpm:120,origin:0}],.01,f=>[f[0].targets[0]<1?0:1]);assert.equal(r.status,'failed');assert.equal(r.reason,'ambiguous_or_unsupported_song_phase');
});
test('conflicting chord component preserves independent clock rows',()=>{
 const p={indices:[0,1],lane_spacing_pixels:40,minimum_velocity_pixels_per_second:500},r=fitGrid([1,1.03125,1.125,1.25],[.001,.001,.001,.001],120,0,[16],0,[p]);
 assert.equal(r.status,'partial');assert.deepEqual(r.targets,[null,null,1.125,1.25]);assert.deepEqual(r.incompatible_chord_indices,[0,1]);assert.equal(r.reason,'native_chord_domains_incompatible');assert.deepEqual(r.unconstrained_row_domains,[[32,32],[33,33],[36,36],[40,40]]);
});
test('application warns on both inconsistent chord members without losing other rows',()=>{
 const d=chord();d.notes.push(structuredClone(d.notes[2]));d.head_registration.notes.push(structuredClone(d.head_registration.notes[2]));
 d.notes.forEach((n,i)=>{const target=[1,1.03125,1.125,1.25][i];Object.assign(n,{lane:i,target_seconds:target,prediction_uncertainty_seconds:.001});if(i>=2)n.points=n.points.map(([t])=>[t,40+500*(target-t)]);d.head_registration.notes[i].note=i;});
 const before=structuredClone(d),r=apply(d);assert.deepEqual(d,before);assert.deepEqual(r.notes.map(n=>n.target_seconds),[null,null,1.125,1.25]);assert.deepEqual(new Set(r.beat_timing.warnings.map(w=>w.note)),new Set([0,1]));assert.equal(r.beat_timing.groups[0].split,16);assert.ok(r.beat_timing.warnings.every(w=>w.failure_detail==='native_chord_domains_incompatible'));
});
