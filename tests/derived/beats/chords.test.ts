/** Concurrent measured heads constrain rows without widening recorded time bounds. */
import {test} from 'node:test';import assert from 'node:assert/strict';
import {chord,apply} from './fixtures.ts';
import {prepare,constrain,conflicts} from '../../../src/piu_timeline/derived/beats/chords.ts';
import {fitGrid} from '../../../src/piu_timeline/derived/beats/grid.ts';
const proof=()=>({...prepare(chord(),40)[0],indices:[0,1]});
test('measured chord resolves one member but retains its original clock domain',()=>{
 const d=chord(),before=structuredClone(d),p=prepare(d,40);assert.equal(p.length,1);assert.deepEqual(p[0].peer_notes,[0,1]);
 const targets=d.notes.map(n=>n.target_seconds),errors=d.notes.map(n=>n.prediction_uncertainty_seconds);
 assert.equal(fitGrid(targets,errors,120,0).reason,'ambiguous_beat_rows');const r=fitGrid(targets,errors,120,0,undefined,0,[{...p[0],indices:[0,1]}]);
 assert.equal(r.split,16);assert.deepEqual(r.rows,[32,32,33]);assert.deepEqual(r.unconstrained_row_domains,[[32,32],[32,33],[33,33]]);assert.deepEqual(d,before);
});
function shared(){const d=chord();d.notes.forEach((n,i)=>{n.lane=[0,5,6][i];const r=d.head_registration.notes[i];Object.assign(r,{status:'measured',coordinate_method:'native_image_anchors'});delete r.coordinate_uncertainty_pixels;
 r.observations.forEach((s,j)=>Object.assign(s,{native_y_pixels:n.points[j][1],template:i<2?'shared':'other'}));});d.layout.lanes=Array.from({length:10},(_,i)=>({x:.05+.1*i}));return d;}
test('identical image reference cancels shared anchor offset without absolute calibration',()=>{
 const d=shared(),before=structuredClone(d),p=prepare(d,40);assert.equal(p.length,1);assert.deepEqual(p[0].peer_notes,[0,1]);assert.equal(p[0].measurement_basis,'shared_image_reference');assert.equal(p[0].reference_identity,'shared');assert.deepEqual(p[0].reference_templates,['shared']);assert.deepEqual(d,before);
});
for(const kind of ['different','changing','gap','stale'])test(`invalid shared reference cannot establish chord: ${kind}`,()=>{
 const d=shared(),r=d.head_registration.notes[1];
 if(kind==='different')r.observations.forEach(s=>s.template='unreviewed_other_reference');
 if(kind==='changing')d.head_registration.notes.slice(0,2).forEach(r=>r.observations.slice(0,3).forEach(s=>s.template='first_pose'));
 if(kind==='gap')d.notes[1].points.forEach((p,j)=>{p[1]+=2;r.observations[j].native_y_pixels+=2;});
 if(kind==='stale'){r.observations[0].native_y_pixels+=1;assert.throws(()=>prepare(d,40));}else assert.deepEqual(prepare(d,40),[]);
});
test('ambiguous joint rows, slow geometry, and incompatible domains remain unresolved',()=>{
 const p=proof();assert.equal(fitGrid([1.015,1.02],[.03,.03],120,0,[16],0,[p]).reason,'ambiguous_beat_rows');
 assert.deepEqual(constrain([[32,32],[32,33]],.03125,[{...p,minimum_velocity_pixels_per_second:50}]),[[[32,32],[32,33]],[]]);
 assert.equal(fitGrid([1,1.03125],[.001,.001],120,0,[16],0,[p]).reason,'native_chord_domains_incompatible');
});
for(const kind of ['gap','short','few','source_pts','unregistered','uncertain','stationary','nonlinear'])test(`unproven measured chord: ${kind}`,()=>{
 const d=chord(),r=d.head_registration.notes[1];
 if(kind==='gap')d.notes[1].points.forEach(p=>p[1]+=2);
 if(kind==='short')d.head_registration.notes.forEach(r=>r.observations=r.observations.slice(0,6));
 if(kind==='few')r.observations=r.observations.slice(0,3);
 if(kind==='source_pts')r.observations[0].source_pts_seconds+=1;
 if(kind==='unregistered')r.coordinate_method='unverified';if(kind==='uncertain')r.coordinate_uncertainty_pixels=2;
 if(kind==='stationary')d.notes.slice(0,2).forEach(n=>n.points.forEach(p=>p[1]=200));
 if(kind==='nonlinear')d.notes.slice(0,2).forEach(n=>n.points[4][1]+=5);
 if(kind==='source_pts')assert.throws(()=>prepare(d,40));else assert.deepEqual(prepare(d,40),[]);
});
test('application uses measured concurrency while retaining original recording ranges',()=>{
 const d=chord(),before=structuredClone(d),r=apply(d);assert.deepEqual(d,before);assert.deepEqual(r.notes.map(n=>n.target_seconds),[1,1,1.03125]);assert.deepEqual(r.notes[1].video_target_range,[.99,1.05]);assert.equal(r.beat_timing.status,'restored');
 assert.deepEqual(r.beat_timing.groups[0].native_chord_constraints[0].source_pts_seconds,d.notes[0].points.map(([t])=>50+t));
});
test('cross-group contradiction remains explicit and leaves evidence unchanged',()=>{
 const d=chord(),p=prepare(d,40);d.notes[1].target_seconds=1.1;const before=structuredClone(d),w=conflicts(d.notes,p);
 assert.deepEqual(new Set(w.map(w=>w.note)),new Set([0,1]));assert.ok(w.every(w=>w.reason==='beat_grid_conflicts_with_native_chord'));assert.deepEqual(d,before);
});
test('fine rows still reject a measurable total chord distance',()=>{
 const p={indices:[0,1],lane_spacing_pixels:40,minimum_velocity_pixels_per_second:500},[r,used]=constrain([[400,400],[412,412],[450,450]],.0025,[p]);
 assert.ok(r.slice(0,2).every(([a,b])=>a>b));assert.deepEqual(r[2],[450,450]);assert.deepEqual(used,[p]);
});
test('fine rows retain every pixel-compatible candidate without forcing equality',()=>{
 const p={indices:[0,1],lane_spacing_pixels:40,minimum_velocity_pixels_per_second:500};assert.deepEqual(constrain([[400,400],[400,405]],.0025,[p]),[[[400,400],[400,402]],[p]]);
 assert.deepEqual(constrain([[500,500],[503,503]],.002,[p])[0],[[500,500],[503,503]]);
});
test('bounded concurrency propagates between peers without collapsing distinct rows',()=>{
 const p=[[0,1],[1,2]].map(indices=>({indices,lane_spacing_pixels:40,minimum_velocity_pixels_per_second:500}));assert.deepEqual(constrain([[10,10],[10,20],[14,14]],.0025,p)[0],[[10,10],[12,12],[14,14]]);
});
