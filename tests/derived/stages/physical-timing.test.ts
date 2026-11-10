/** Saved observations and stage ownership, independently of any recording or song. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {capture,materialize as coordinates} from '../../../src/piu_timeline/derived/stages/coordinates.ts';
import {reconstruct,materialize} from '../../../src/piu_timeline/derived/stages/physical_timing.ts';
import {boundArtifact} from '../../../src/piu_timeline/derived/stages/contracts.ts';
import {nativeScene} from '../fixtures.ts';
function scene(spacing=40,fps=60,repeated=false){
 const data=nativeScene([[.85,0],[.85,1],[1.1,2]],spacing,fps,5,{end:1.3,...(repeated?{repeated:[[.5,.5+1/fps]] as [number,number][]}:{})});
 data.frame_timeline=data.scroll_motion.samples.map(({time,source_pts})=>({time,source_pts}));
 return data;
}
for(const spacing of [20,40,80])for(const fps of [30,60,120])for(const repeated of [false,true])test(`physical timing from saved coordinates: spacing=${spacing}, fps=${fps}, repeated=${repeated}`,()=>{
 const data=scene(spacing,fps,repeated),before=structuredClone(data),source=capture(data),plain=coordinates(source);
 assert.ok(plain.notes.every(n=>!('target_seconds'in n)&&!('status'in n)));
 assert.ok(!('scroll_motion'in plain));
 const output=reconstruct(source),result=materialize(output);
 assert.deepEqual(data,before);assert.deepEqual(source,capture(data));
 assert.deepEqual(result.notes.map(n=>n.points),plain.notes.map(n=>n.points));
 for(const [i,target]of [.85,.85,1.1].entries()){
  assert.equal(result.notes[i].status,'estimated');
  assert.ok(Math.abs(result.notes[i].target_seconds-target)<=result.notes[i].prediction_uncertainty_seconds+1e-8);
 }
 assert.ok(Math.abs(result.notes[0].target_seconds-result.notes[1].target_seconds)<1e-9);
 assert.deepEqual(result.scroll_motion.samples.map(s=>s.source_pts),data.frame_timeline.map(s=>s.source_pts));
});
test('physical results cannot edit coordinates, borrow another input or depend on popup values',()=>{
 const data=scene(),source=capture(data),first=reconstruct(source);
 data.matches=[{note:0,target_seconds:999}];data.combo_events=[{delta:10,lower_seconds:0,upper_seconds:9}];
 assert.deepEqual(reconstruct(capture(data)),first);
 const changed=scene();changed.notes[0].points[0][1]++;
 assert.throws(()=>materialize({...capture(changed),physical_timing:first.physical_timing}),/different inputs/);
 const foreign=boundArtifact('physical-timing',source,{...first.physical_timing.data,notes:[{note:0,values:{points:[]}}]});
 assert.throws(()=>materialize({...source,physical_timing:foreign as never}),/Foreign/);
});
test('physical timing preserves explicit failures without requiring musical reference or input evidence',()=>{
 const data=scene();data.notes.forEach((n,i)=>{n.points=n.points.map(([t,y])=>[t,y+i*70*t]);});
 const result=materialize(reconstruct(capture(data)));
 assert.equal(result.timing_reconstruction.status,'failed');
 assert.ok(result.timing_reconstruction.warnings.length);
 assert.ok(result.notes.some(n=>n.status==='excluded'&&n.target_seconds===null));
});
test('coincident cap components are classified without deleting observed trajectories',()=>{
 const data=scene();data.notes=[data.notes[0],{...structuredClone(data.notes[0]),points:data.notes[0].points.map(([t,y])=>[t,y+1])}];
 data.head_registration.notes=data.head_registration.notes.slice(0,1);
 const source=capture(data),result=materialize(reconstruct(source));
 assert.equal(result.notes.length,2);
 assert.equal(result.notes.filter(n=>n.reason==='duplicate_head_component').length,1);
 assert.deepEqual(result.notes.map(n=>n.points),coordinates(source).notes.map(n=>n.points));
});
