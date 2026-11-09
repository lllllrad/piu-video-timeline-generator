/** Concurrent measured heads constrain rows without widening recorded time bounds. */
import {test} from 'node:test';import assert from 'node:assert/strict';
import {contracts}from '../../../src/piu_timeline/derived/contracts.ts';
import {measuredGapScene}from '../fixtures.ts';
import {chord,apply} from './fixtures.ts';
import {prepare,constrain,conflicts} from '../../../src/piu_timeline/derived/beats/chords.ts';
import {fitGrid} from '../../../src/piu_timeline/derived/beats/grid.ts';
import {resolve} from '../../../src/piu_timeline/derived/skins/localization.ts';
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

for(const spacing of [20,40,80])for(const fps of [30,60,120])for(const hidden of [false,true])
test(`source-certified concurrency survives capture delay and paired visibility loss: spacing=${spacing}, fps=${fps}, hidden=${hidden}`,()=>{
 const d=measuredGapScene(spacing,fps,[[.85,0],[.85,1]],{renderTime:t=>t-.012*Math.sin(2*Math.PI*(t-.2)/.4)});
 if(hidden){
  d.notes.forEach(n=>n.points=n.points.filter(([t])=>!(.4<t&&t<.55)));
  d.head_registration.notes.forEach(r=>r.observations=r.observations.filter(o=>!(.4<o.time&&o.time<.55)));
 }
 const before=structuredClone(d),proofs=prepare(d,spacing);assert.equal(proofs.length,1);
 const p=proofs[0],model=p.capture_phase_motion;assert.ok(model);
 assert.ok(model.velocity_range_pixels_per_second[0]<=6*spacing&&6*spacing<=model.velocity_range_pixels_per_second[1]);
 assert.ok(model.source_frames>p.observed_points||!hidden);
 const indexed={...p,indices:[0,1]};assert.deepEqual(constrain([[0,0],[0,1]],.125,[indexed])[0],[[0,0],[0,0]]);
 assert.deepEqual(d,before);
});

test('capture-aware chord support preserves physically compatible distinct fine rows',()=>{
 const d=measuredGapScene(40,60,[[.85,0],[.852,1]],{renderTime:t=>t-.012*Math.sin(2*Math.PI*(t-.2)/.4)}),p=prepare(d,40)[0];
 assert.ok(p?.capture_phase_motion);
 assert.deepEqual(constrain([[400,400],[401,401]],.002,[{...p,indices:[0,1]}])[0],[[400,400],[401,401]]);
});
for(const missing of [false,true])test(`nonuniform motion or absent original capture cannot borrow a jitter budget: missing=${missing}`,()=>{
 const d=measuredGapScene(40,60,[[.85,0],[.85,1]],{renderTime:missing?
  t=>t-.012*Math.sin(2*Math.PI*(t-.2)/.4):t=>t-Math.min(.2,Math.max(0,t-.3))});
 if(missing){
  d.notes.forEach(n=>n.points=n.points.filter(([t])=>!(.4<t&&t<.55)));
  d.head_registration.notes.forEach(r=>r.observations=r.observations.filter(o=>!(.4<o.time&&o.time<.55)));
  d.scroll_motion.samples=d.scroll_motion.samples.filter(s=>!(.4<s.time&&s.time<.55));
 }
 assert.deepEqual(prepare(d,40),[]);
});

for(const spacing of [19.25,38.5,77])test(`sampled-image localization cannot inherit a blanket source/search budget: spacing=${spacing}`,()=>{
 const d=measuredGapScene(spacing,60,[[.85,0],[.85,1]]);
 d.head_registration.format=structuredClone(contracts.image_coordinates);
 assert.throws(()=>prepare(d,spacing),/missing_image_localization/);
});

test('a source gap excluding zero cannot become an exact chord on a coarse grid',()=>{
 const p={indices:[0,1],peer_notes:[0,1],lane_spacing_pixels:40,minimum_velocity_pixels_per_second:500,
  native_gap_range_pixels:[1,2],capture_phase_motion:{velocity_range_pixels_per_second:[500,510]}};
 assert.ok(constrain([[0,0],[0,1]],.125,[p])[0].every(([lo,hi])=>lo>hi));
 assert.deepEqual(constrain([[0,0],[0,3]],.002,[p])[0],[[0,0],[1,2]]);
 const notes=[{lane:0,points:[],prediction_uncertainty_seconds:.01,status:'estimated',target_seconds:0},{lane:1,points:[],prediction_uncertainty_seconds:.01,status:'estimated',target_seconds:.003}];
 assert.deepEqual(conflicts(notes,[p]),[]);
 for(const target of [0,-.003,.005]){notes[1].target_seconds=target;assert.equal(conflicts(notes,[p]).length,2);}
});

function exactGap(spacing:number,gap:number,jitter:number){
 const d=measuredGapScene(spacing,60,[[.85,0],[.85,1]]);
 d.notes[1].points=d.notes[0].points.map(([t,y],i)=>[t,y+gap+(i%2?jitter:0)]);
 d.head_registration.format=structuredClone(contracts.image_coordinates);
 d.head_registration.notes.forEach((r,i)=>r.observations.forEach((s,j)=>{
  const y=d.notes[i].points[j][1];
  Object.assign(s,resolve({height:d.analysis_height,raw_y:y,comparisons:[{
   template:s.template,comparison_index:0,image_y:y/d.analysis_height,cap_error:0,maximum_error:.015,
   scale_y:spacing/40,same_cap:true,center_offset_y_pixels:0,reference:'generated-reference',
   localization_pixels:{method:'visible_cap_rgb_and_vertical_contrast',compared_pixels:400,
    vertical_contrast_pixels:80,squared_rgb_error:0,vertical_contrast_error:0}}]}).measurement);
  d.notes[i].points[j][1]=s.native_y_pixels;
 }));
 return d;
}
for(const spacing of [20,40,80])for(const gap of [0,.25,-.25])
test(`zero-radius measured gaps tolerate only arithmetic roundoff: spacing=${spacing}, gap=${gap}`,()=>{
 const d=exactGap(spacing,gap,Number.EPSILON*128),before=structuredClone(d),proofs=prepare(d,spacing);
 assert.equal(proofs.length,1);
 const p=proofs[0],[lo,hi]=p.native_gap_range_pixels;
 assert.ok(lo<=hi&&Math.abs(lo-gap)<1e-11&&Math.abs(hi-gap)<1e-11);
 assert.ok(p.endpoint_uncertainty_pixels.every(pair=>pair.every(e=>e===0)));
 const domains=constrain([[0,0],[0,0]],.125,[{...p,indices:[0,1]}])[0];
 assert.deepEqual(domains,gap===0?[[0,0],[0,0]]:[[1,0],[1,0]]);
 assert.deepEqual(d,before);
});
test('a changing measured gap exceeding roundoff supplies no chord proof',()=>{
 assert.deepEqual(prepare(exactGap(40,.25,1e-10),40),[]);
});
