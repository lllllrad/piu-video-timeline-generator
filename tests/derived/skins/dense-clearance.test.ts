import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import type {RecordData} from '../../../src/piu_timeline/derived/types.ts';

const scenes=[.5,1,1.5,2].flatMap(scale=>[22,24].map(gap=>({
 id:`dense-taps-${gap}-${scale}`,lanes:5,scale,fps:60,seed:17,
 duration_seconds:.8,scroll_lane_spacings_per_second:1,role_clearance:true,
 objects:[0,4].flatMap(lane=>Array.from({length:5},(_,i)=>({lane,kind:'tap',y:90+i*gap}))),
})));
const holds=[.5,1,1.5,2].flatMap(scale=>[42,44].map(gap=>({
 id:`overlapping-holds-${gap}-${scale}`,lanes:5,scale,fps:60,seed:19,
 duration_seconds:.8,scroll_lane_spacings_per_second:1,role_clearance:true,
 objects:[0,4].flatMap(lane=>Array.from({length:4},(_,i)=>({lane,kind:'hold',y:80+i*gap,end_y:110+i*gap}))),
})));
const results:RecordData[]=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-m','tests.play.skins.scenes'],{
 input:JSON.stringify([...scenes,...holds]),encoding:'utf8',maxBuffer:32*1024*1024,
}));

for(const scene of scenes)test(`visible narrow gaps identify dense taps: ${scene.id}`,()=>{
 const result=results.find(r=>r.id===scene.id)!;
 assert.equal(result.notes.length,scene.objects.length,'each cap has its own acquired identity');
 assert.ok(result.frames.every(f=>f.caps.length===scene.objects.length));
 assert.ok(result.roles.every(n=>n.status==='tap'),'separate caps are not unknown merely because the whole reference band is occupied');
 assert.deepEqual(result.connections,[],'nearby caps cannot become holds');
 for(const role of result.roles){
  const proofs=role.observations.filter(o=>o.reason==='image_cap_with_native_clearance');
  assert.ok(proofs.length>0||role.observations.some(o=>o.role==='tap'&&o.classification_status==='full_pattern'),
   'a role requires an actual gap proof or the full original tap pattern');
  for(const proof of proofs){
   assert.equal(proof.source_pts_seconds,42.125+proof.playback_seconds);
   assert.equal(proof.clearance_regions.length,2);
   for(const region of proof.clearance_regions){
    const alternatives=region.attachment_alternatives??[region];
    for(const part of alternatives){
     assert.ok(part.separating_rows_pixels.length>0);
     assert.equal(part.relaxed_foreground_pixels,0);
     assert.ok(part.separating_rows_pixels.every(y=>y>=part.bounds_pixels[1]&&y<part.bounds_pixels[3]));
    }
   }
  }
 }
});

for(const scene of holds)test(`overlapping hold caps do not supply false tap separation: ${scene.id}`,()=>{
 const result=results.find(r=>r.id===scene.id)!;
 assert.equal(result.notes.length,scene.objects.length*2);
 assert.ok(result.roles.every(n=>n.status==='hold'));
 assert.ok(result.roles.every(n=>n.observations.every(o=>o.kind!=='tap')));
 assert.equal(result.connections.length,scene.objects.length);
 const owns=(note:number,y:number)=>{
  const observed=result.coordinates.notes[note].observations.find(o=>o.time===0);
  assert.ok(observed,'the endpoint has independent native image coordinates');
  assert.ok(Number.isFinite(observed.native_cap_projection_uncertainty_pixels));
  return Math.abs(observed.native_y_pixels-y*scene.scale)<=observed.native_cap_projection_uncertainty_pixels+1e-8;
 };
 for(const expected of scene.objects){
  const connections=result.connections.filter(h=>h.lane===expected.lane&&
   owns(h.head_note,expected.y)&&owns(h.tail_note,expected.end_y));
  assert.equal(connections.length,1,'each hold keeps its own caps, without spanning a neighboring hold');
 }
});
