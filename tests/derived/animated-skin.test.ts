import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import type {RecordData} from '../../src/piu_timeline/derived/types.ts';

const scenes:RecordData[]=[];
for(const skin of [undefined,'shouldered'])for(const scale of [.5,1,1.5])scenes.push({
 id:`animated-${skin??'flat'}-${scale}`,skin_profile:skin,scale,
 objects:[{kind:'hold',lane:0,y:80,end_y:skin?102:160},
  {kind:'hold',lane:2,y:120,end_y:180},{kind:'tap',lane:1,y:100}]});
for(const skin of [undefined,'shouldered'])scenes.push({
 id:`missing-appearance-${skin??'flat'}`,skin_profile:skin,scale:1,reference_appearance_phases:1,
 objects:[{kind:'hold',lane:0,y:80,end_y:skin?102:160},{kind:'tap',lane:1,y:100}]});
for(const s of scenes)Object.assign(s,{lanes:5,fps:60,seed:71,appearance_phases:4});
const results:RecordData[]=JSON.parse(execFileSync('sh',[
 'scripts/run.sh','.venv/bin/python','-m','tests.play.skins.scenes'],{
 input:JSON.stringify(scenes),encoding:'utf8',maxBuffer:32*1024*1024}));

for(const scene of scenes.filter(s=>!s.reference_appearance_phases))test(`known cap animation keeps identities and hold endpoints: ${scene.id}`,()=>{
 const r=results.find(r=>r.id===scene.id)!;
 const endpoints=scene.objects.flatMap(o=>o.kind==='tap'?[{...o,role:'tap'}]:[
  {lane:o.lane,y:o.y,role:'hold_start'},{lane:o.lane,y:o.end_y,role:'hold_end'}]);
 assert.equal(r.notes.length,endpoints.length);
 assert.equal(r.source_preserved,true);
 assert.deepEqual(r.frames.map(f=>f.pts),r.expected_source_pts);
 for(const [i,frame]of r.frames.entries()){
  assert.equal(frame.caps.length,endpoints.length);
  for(const e of endpoints){
   const expected=Math.round(e.y-80*i/scene.fps)*scene.scale;
   const found=frame.caps.filter(c=>c.lane===e.lane&&Math.abs(c.y*300*scene.scale-expected)<1e-6);
   assert.equal(found.length,1);assert.equal(found[0].role,e.role);
  }
 }
 assert.ok(r.notes.every(n=>n.points.length===r.frames.length),'no pose can disappear between recognized poses');
 assert.ok(r.roles.every(n=>n.status!=='conflict'&&n.status!=='unknown'));
 assert.equal(r.connections.length,2,'an animated tail remains part of its hold');
 assert.deepEqual(r.warnings,[]);
});
for(const scene of scenes.filter(s=>s.reference_appearance_phases))test(`an incomplete appearance bank exposes native detection gaps: ${scene.id}`,()=>{
 const r=results.find(r=>r.id===scene.id)!;
 assert.ok(r.frames.some(f=>f.caps.length===3));
 assert.ok(r.frames.some(f=>f.caps.length<3));
 assert.ok(r.warnings.length>0,'missing appearances cannot be silently supplied by neighboring frames');
 assert.deepEqual(r.frames.map(f=>f.pts),r.expected_source_pts);
});
