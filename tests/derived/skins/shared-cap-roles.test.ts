import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import type {RecordData} from '../../../src/piu_timeline/derived/types.ts';

const scenes:RecordData[]=[];
for(const scale of [.5,1,1.5])for(const skin of [undefined,'shouldered']){
 const base={scale,skin_profile:skin,lanes:5,fps:60,seed:71,appearance_phases:3,
  reference_role_appearance_phases:{hold_start:1,hold_end:1},
  objects:[{lane:0,kind:'hold',y:80,end_y:150},{lane:4,kind:'hold',y:90,end_y:180},
   {lane:2,kind:'tap',y:100}]};
 for(const share of [false,true])scenes.push({...base,id:`${skin??'flat'}-${scale}-${share}`,share_cap_appearances:share});
}
const results:RecordData[]=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-m','tests.play.skins.scenes'],{
 input:JSON.stringify(scenes),encoding:'utf8',maxBuffer:64*1024*1024}));
for(const scene of scenes)test(`independent role context with uneven appearance references: ${scene.id}`,()=>{
 const r=results.find(r=>r.id===scene.id)!;
 assert.equal(r.notes.length,5);assert.deepEqual(r.frames.map(f=>f.pts),r.expected_source_pts);
 if(!scene.share_cap_appearances){
  assert.ok(r.frames.some(f=>f.caps.some(c=>c.role==='unknown')),'missing role-specific poses reproduce the original failure');
  return;
 }
 assert.equal(r.connections.length,2,'each real hold keeps its own endpoints');
 assert.deepEqual(r.warnings,[]);
 for(const [i,frame]of r.frames.entries()){
  assert.equal(frame.caps.length,5);
  for(const obj of scene.objects){
   const endpoints=obj.kind==='tap'?[[obj.y,'tap']]:[[obj.y,'hold_start'],[obj.end_y,'hold_end']];
   for(const [y,role]of endpoints){
    const expected=Math.round(Number(y)-80*i/scene.fps)*scene.scale;
    const cap=frame.caps.filter(c=>c.lane===obj.lane&&Math.abs(c.y*300*scene.scale-expected)<1e-6);
    assert.equal(cap.length,1);assert.equal(cap[0].role,role);
    if(cap[0].shared_role){
     assert.equal(cap[0].shared_role.context.role,role);
     assert.ok(cap[0].shared_role.context.connection_rows_pixels.length);
     assert.ok(cap[0].shared_role.context.region_errors.connection<=.002);
    }
   }
  }
 }
 assert.ok(r.roles.flatMap(n=>n.observations).some(o=>o.shared_role),'role consumer retains independent proof');
 for(const note of r.coordinates.notes){
  assert.equal(note.coordinate_status,'projected','use the measured cap reference, never the context anchor');
  assert.deepEqual(note.observations.map(o=>o.source_pts_seconds),r.expected_source_pts);
 }
});
