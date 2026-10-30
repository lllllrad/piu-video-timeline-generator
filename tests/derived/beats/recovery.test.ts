/** Recovery freezes independent references and cannot validate itself. */
import {test} from 'node:test';import assert from 'node:assert/strict';
import {recovery,rejected,sparse,spatial,apply,near} from './fixtures.ts';
import {prepare,predictions} from '../../../src/piu_timeline/derived/beats/coordinates.ts';
import {recover,chooseRow} from '../../../src/piu_timeline/derived/beats/recovery.ts';
import {spacingFailures} from '../../../src/piu_timeline/derived/beats/spacing.ts';
const sections=[[0,4,120]];
test('independent native proof replaces failed clock without rewriting original positions',()=>{
 const d=recovery(),before=structuredClone(d),s=prepare(d,40,true),r=recover(d.notes,s,sections,0,0,.01),n=d.notes[4],p=r[4];
 assert.equal(n.status,'estimated');assert.equal(n.target_seconds,1.5);assert.deepEqual(n.points,before.notes[4].points);assert.ok(!Object.hasOwn(n,'motion_clock'));
 assert.deepEqual(n.timing_reconstruction.previous_motion_attempt,before.notes[4].timing_reconstruction);assert.ok(!p.models[0].model.references.some(r=>r.note===4));assert.ok(n.prediction_uncertainty_seconds>.01);
 assert.deepEqual(p.models[0].head.source_pts_range,[80.5,80.68]);assert.deepEqual(spacingFailures(d.notes,40,d.scroll_motion,s),[]);
 n.target_seconds+=.06;assert.ok(spacingFailures(d.notes,40,d.scroll_motion,s).some(w=>w.peer_notes.includes(4)));
});
test('recovery references support sparse gaps without admitting recovered heads as references',()=>{
 const d=recovery(),s=prepare(d,40,true),r=recover(d.notes,s,sections,0,0,0),refs=r[4].models[0].model.references;
 assert.deepEqual(predictions(4,5,d.notes,[.5,.68],s,.1),[]);s.recovery_reference_sets=[{note:4,chunk:0,references:refs}];
 const models=predictions(4,5,d.notes,[.5,.68],s,.1);assert.ok(models.length);assert.ok(models.every(m=>m.references.every(r=>![4,5].includes(r.note))));assert.deepEqual(spacingFailures(d.notes,40,d.scroll_motion,s),[]);
 d.notes[4].target_seconds+=.06;assert.deepEqual(new Set(spacingFailures(d.notes,40,d.scroll_motion,s).map(w=>w.note)),new Set([4]));
 s.recovery_reference_sets[0].references=[...refs,{note:4,target_seconds:d.notes[4].target_seconds,...s.chunks[0][4]}];assert.deepEqual(predictions(4,5,d.notes,[.5,.68],s,.1),[]);
});
test('adding a head cannot hide a prior pair by changing adjacency',()=>{
 const d=spatial();d.motion.coordinate_registration.chunks[0].head_offsets[1].offset_pixels+=8;assert.ok(spacingFailures(d.notes,40,d.motion).length);
 d.notes.push({status:'estimated',lane:2,points:d.notes[0].points.map(([t,y])=>[t,y+30]),target_seconds:1.25,motion_target_phase:300,motion_clock:{origin:0,velocity:240,intercept:0}});
 assert.ok(spacingFailures(d.notes,40,d.motion,null,null,[0,1]).some(w=>w.peer_notes.join()==='0,1'));
});
test('simultaneously recovered neighbors never become mutual references',()=>{
 const d=recovery([4,5]),r=recover(d.notes,prepare(d,40,true),sections,0,0,0);assert.deepEqual(Object.keys(r).filter(i=>r[i].status==='restored'),['4','5']);
 assert.ok(Object.values(r).every(p=>p.models.every(m=>m.model.references.every(r=>![4,5].includes(r.note)))));
});
for(const kind of ['few','unmeasured','bad','unbracketed','no_phase','tempo'])test(`invalid recovery stays excluded: ${kind}`,()=>{
 const d=recovery(),n=d.notes[4];
 if(kind==='few')d.head_registration.notes.slice(0,4).forEach(r=>Object.assign(r,{status:'unresolved',coordinate_method:'unverified'}));
 if(kind==='unmeasured')Object.assign(d.head_registration.notes[4],{status:'unresolved',coordinate_method:'unverified'});
 if(kind==='bad'){d.notes[2].points.forEach(p=>p[1]+=10);d.scroll_motion.coordinate_registration.chunks[0].head_offsets[2].offset_pixels+=10;}
 if(kind==='unbracketed'){n.points.forEach(p=>p[1]-=180);d.scroll_motion.coordinate_registration.chunks[0].head_offsets[4].offset_pixels-=180;}
 recover(d.notes,prepare(d,40,true),kind==='tempo'?[[0,1.51,120],[1.51,4,240]]:sections,0,kind==='no_phase'?null:0,0);assert.equal(n.status,'excluded');assert.equal(n.target_seconds,null);
});
test('ambiguous and contradictory coordinate models cannot select a finer row',()=>{
 const models=[{range:[1.37,1.63],model:{references:Array.from({length:8},(_,i)=>({target_seconds:1+i*.125}))}}];assert.equal(chooseRow(models,sections,0,0).reason,'ambiguous_native_coordinate_rows');
 models.push({...models[0],range:[1.8,1.9]});assert.equal(chooseRow(models,sections,0,0).reason,'incompatible_native_coordinate_models');
});
for(const reason of ['shared_timing_reconstruction_failed','shared_spacing_reconstruction_conflict'])test(`application retires only independently proven warning: ${reason}`,()=>{
 const d=recovery();d.notes[4].reason=reason;d.timing_reconstruction.warnings[0].reason=reason;d.timing_reconstruction.warnings.push({note:4,reason:'shared_motion_observation_conflict'});
 const before=structuredClone(d),r=apply(d);assert.equal(r.notes[4].target_seconds,1.5);assert.deepEqual(r.timing_reconstruction.warnings,[{note:4,reason:'shared_motion_observation_conflict'}]);assert.equal(r.timing_reconstruction.status,'failed');
 assert.equal(r.timing_reconstruction.restored_notes,9);assert.ok(r.beat_timing.native_coordinate_recovery.length);assert.equal(r.beat_timing.native_coordinate_recovery[0].source_failure,reason);assert.deepEqual(d,before);
 if(reason==='shared_spacing_reconstruction_conflict'){const bad=structuredClone(d);bad.notes[4].points[0][1]+=3;const result=apply(bad);assert.equal(result.notes[4].status,'excluded');assert.ok(result.timing_reconstruction.warnings.some(w=>w.reason===reason));}
});
for(const reason of ['beat_grid_conflicts_with_spatial_spacing','beat_grid_conflicts_with_native_chord'])test(`external rows must independently prove rejected geometry: ${reason}`,()=>{
 for(const unique of [true,false]){const [d,g]=rejected(),n=d.notes[4];n.reason=reason;n.beat_reconstruction.reason=reason;
 if(!unique)g.slice(1).forEach(g=>g.unconstrained_row_domains.forEach(r=>r[1]++));
 const p=recover(d.notes,prepare(d,40,true),sections,0,0,0,g,[0,0])[4];assert.equal(n.status,unique?'estimated':'excluded');
 if(unique){assert.equal(n.target_seconds,1.5);assert.equal(p.source_failure,reason);assert.deepEqual(p.excluded_reference_group,[3,4,5]);assert.equal(n.timing_reconstruction.rejected_beat_assignment.reason,reason);}}
});
test('ambiguous clock retains its original bound while geometry chooses',()=>{
 const [d,g]=rejected();d.notes[4].beat_reconstruction.reason='ambiguous_beat_rows';d.notes[4].video_target_range=[1.37,1.63];const r=recover(d.notes,prepare(d,40,true),sections,0,0,0,g,[0,0]);assert.equal(d.notes[4].target_seconds,1.5);assert.deepEqual(r[4].clock_constraint_range,[1.37,1.63]);
});
test('unique external rows prove a target outside a rejected interval without discarding source clock',()=>{
 const [d,g]=rejected(),before=structuredClone(d),r=recover(d.notes,prepare(d,40,true),sections,0,0,.01,g,[-.0005,.0005]),n=d.notes[4],p=r[4];
 assert.equal(n.target_seconds,1.5);assert.ok(n.target_seconds<before.notes[4].video_target_range[0]);assert.deepEqual(n.points,before.notes[4].points);assert.deepEqual(n.motion_clock,before.notes[4].motion_clock);
 assert.deepEqual(p.source_timing.range,[1.519,1.522]);assert.equal(p.source_timing.independent,true);assert.deepEqual(n.timing_reconstruction.rejected_beat_assignment,before.notes[4].beat_reconstruction);assert.deepEqual(p.excluded_reference_group,[3,4,5]);
 assert.ok(p.models.every(m=>new Set(m.model.references.map(r=>r.note)).size===6&&m.model.references.every(r=>[0,1,2,6,7,8].includes(r.note))));
});
for(const kind of ['refined','phase','few','contradiction','other'])test(`external references cannot prove rejected row: ${kind}`,()=>{
 const [d,g]=rejected();let range=[-.0005,.0005];
 if(kind==='refined')g.slice(1).forEach(g=>g.unconstrained_row_domains.forEach(r=>r[1]++));
 if(kind==='phase')range=[-.002,.002];if(kind==='few')d.head_registration.notes.slice(0,3).forEach(r=>Object.assign(r,{status:'unresolved',coordinate_method:'unverified'}));
 if(kind==='contradiction'){d.notes[0].points.forEach(p=>p[1]+=10);d.scroll_motion.coordinate_registration.chunks[0].head_offsets[0].offset_pixels+=10;}
 if(kind==='other')d.notes[4].beat_reconstruction.reason='ambiguous_beat_rows';
 recover(d.notes,prepare(d,40,true),sections,0,0,0,g,range);assert.equal(d.notes[4].status,'excluded');assert.equal(d.notes[4].target_seconds,null);
});
for(const kind of ['valid','bad_reference','ambiguous','pair_failure'])test(`complete sparse native block recovery: ${kind}`,()=>{
 const [d,g]=sparse();if(kind==='bad_reference'){d.notes[0].points.forEach(p=>p[1]+=4);d.scroll_motion.coordinate_registration.chunks[0].head_offsets[0].offset_pixels+=4;}
 if(kind==='ambiguous')g[0].unconstrained_row_domains.forEach(r=>r[1]++);
 if(kind==='pair_failure'){d.notes[4].points.forEach(p=>p[1]+=2.4);d.scroll_motion.coordinate_registration.chunks[0].head_offsets[4].offset_pixels+=2.4;}
 const before=structuredClone(d),r=recover(d.notes,prepare(d,40,true),[[0,8,120]],0,0,0,g,[0,0],40,d.scroll_motion);
 if(kind==='valid'){assert.equal(d.notes[4].target_seconds,4.5);assert.equal(r[4].reference_scope,'complete_native_block');assert.ok(r[4].models.every(m=>m.model.references.length===8&&m.model.references.every(r=>r.note!==4&&Math.abs(r.target_seconds-4.48)>.75)));assert.deepEqual(d.notes[4].points,before.notes[4].points);}
 else{assert.deepEqual(d,before);if(kind==='pair_failure'){assert.equal(r[4].status,'failed');assert.equal(r[4].reason,'native_block_recovery_failed_pair_validation');}else assert.ok(!Object.hasOwn(r,4));}
});
