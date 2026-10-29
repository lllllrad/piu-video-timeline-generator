import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import type {RecordData} from '../../src/piu_timeline/derived/types.ts';

const tap=(lane:number,y=80)=>({kind:'tap',lane,y});
const hold=(lane:number,y=80,end_y=102)=>({kind:'hold',lane,y,end_y});
const scenes:RecordData[]=[];
for(let lane=0;lane<5;lane++)for(const kind of ['hold','taps'])scenes.push({
 id:`near-${kind}-lane${lane}`,objects:kind==='hold'?[hold(lane)]:[tap(lane),tap(lane,102)],scale:1});
for(const scale of [.5,1.5,2])for(const kind of ['hold','taps'])scenes.push({
 id:`near-${kind}-scale${scale}`,objects:kind==='hold'?[hold(2)]:[tap(2),tap(2,102)],scale});
for(const scale of [.5,1,2])scenes.push({id:`long-hold-scale${scale}`,objects:[hold(1,80,160)],scale});
for(const scale of [.5,1]){
 scenes.push({id:`close-chord-scale${scale}`,objects:[hold(0),hold(2),tap(3),tap(3,102)],scale});
 scenes.push({id:`neighboring-held-intervals-scale${scale}`,objects:[hold(0),hold(0,140,162),tap(1,90)],scale});
}
for(const kind of ['hold','taps'])scenes.push({
 id:`encoded-near-${kind}`,objects:kind==='hold'?[hold(2)]:[tap(2),tap(2,102)],scale:.5,capture:'encoded'});
for(const scale of [.5,1])scenes.push({id:`hidden-connection-scale${scale}`,objects:[hold(2)],scale,mode:'opaque_connection'});
for(const s of scenes)Object.assign(s,{lanes:5,fps:60,seed:41,skin_profile:'shouldered'});
const acquire=(items:RecordData[]):RecordData[]=>JSON.parse(execFileSync('sh',[
 'scripts/run.sh','.venv/bin/python','-m','tests.play.skins.scenes'],{
 input:JSON.stringify(items),encoding:'utf8',maxBuffer:32*1024*1024}));
const results=[...acquire(scenes.filter(s=>!s.capture)),...acquire(scenes.filter(s=>s.capture))];

for(const scene of scenes.filter(s=>!s.mode))test(`cut-corner caps retain near-touching holds versus separate taps: ${scene.id}`,()=>{
 const r=results.find(r=>r.id===scene.id)!;
 const endpoints=scene.objects.flatMap(o=>o.kind==='tap'?[{...o,role:'tap'}]:[
  {lane:o.lane,y:o.y,role:'hold_start'},{lane:o.lane,y:o.end_y,role:'hold_end'}]);
 assert.equal(r.notes.length,endpoints.length);
 assert.equal(r.source_preserved,true);
 assert.deepEqual(r.frames.map(f=>f.pts),r.expected_source_pts);
 for(const [i,f]of r.frames.entries()){
  assert.equal(f.caps.length,endpoints.length,'every visible endpoint must survive the neighboring border');
  for(const e of endpoints){
   const y=Math.round(e.y-80*i/scene.fps)*scene.scale;
   const found=f.caps.filter(c=>c.lane===e.lane&&Math.abs(c.y*300*scene.scale-y)<1e-6);
   assert.equal(found.length,1);
   assert.equal(found[0].role,e.role,'a connected tail cannot become an independent tap');
  }
 }
 for(const e of endpoints){
  const index=r.notes.findIndex(n=>n.lane===e.lane&&Math.abs(n.points[0][1]-e.y*scene.scale)<1e-6);
  assert.ok(index>=0);assert.equal(r.notes[index].points.length,r.frames.length);
  assert.equal(r.roles[index].status,e.role==='tap'?'tap':'hold');
  assert.deepEqual(r.roles[index].observations.map(o=>o.source_pts_seconds),r.expected_source_pts);
 }
 const holds=scene.objects.filter(o=>o.kind==='hold');
 assert.equal(r.connections.length,holds.length,'one connected image object per hold, never a spanning object');
 for(const h of holds){
  const found=r.connections.filter(c=>c.lane===h.lane&&Math.abs(r.notes[c.head_note].points[0][1]-h.y*scene.scale)<1e-6&&
   Math.abs(r.notes[c.tail_note].points[0][1]-h.end_y*scene.scale)<1e-6);
  assert.equal(found.length,1);
  assert.deepEqual([...new Set(found[0].image_connection_evidence.map(p=>p.source_pts))],r.expected_source_pts);
 }
 assert.deepEqual(r.warnings,[]);
});

for(const scene of scenes.filter(s=>s.mode))test(`near-touching caps cannot prove a hold without their connector: ${scene.id}`,()=>{
 const r=results.find(r=>r.id===scene.id)!;
 assert.equal(r.notes.length,2);
 for(const [i,f]of r.frames.entries()){
  assert.ok(f.caps.length<=2,'an obscured connection cannot create another cap');
  for(const c of f.caps){
   assert.equal(c.lane,2);assert.equal(c.role,'unknown');
   assert.ok([80,102].some(y=>Math.abs(c.y*300*scene.scale-Math.round(y-80*i/scene.fps)*scene.scale)<1e-6));
  }
 }
 // At half size the white gap enters the cap's interpolation stencil; those
 // frames do not contain the unchanged positive cap used by the clear oracle.
 if(scene.scale===1)assert.ok(r.frames.every(f=>f.caps.length===2));
 else assert.ok(r.warnings.some(w=>w.failure_detail==='skin_body_images_without_complete_endpoint_ownership'));
 assert.ok(r.roles.every(n=>n.status==='unknown'),'shape proximity cannot supply a tap or hold role');
 assert.deepEqual(r.connections,[]);
});
