import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import type {RecordData} from '../../src/piu_timeline/derived/types.ts';

const tap=(lane:number,y=80)=>({kind:'tap',lane,y});
const hold=(lane:number,y=80,end_y=106)=>({kind:'hold',lane,y,end_y});
const cases:[string,RecordData[],number][]=[
 ['empty',[],5],
 ['single-chord',Array.from({length:5},(_,i)=>tap(i)),5],
 ['double-stagger',Array.from({length:10},(_,i)=>tap(i,80+2*i)),10],
 ['short-hold',[hold(2)],5],
 ['long-hold',[hold(1,80,160)],5],
 ['two-taps',[tap(2),tap(2,106)],5],
 ['adjacent-holds',[hold(0),hold(0,140,166)],5],
 ['independent-tap',[hold(4,80,160),tap(4,200)],5],
];
const scenes=cases.flatMap(([name,objects,lanes])=>[.5,1.5,2].map(scale=>({
 id:`${name}-${scale}`,objects,lanes,scale,fps:60,seed:41,capture:'encoded'})));
const limited=[tap(2),hold(2)].map((object,i)=>({id:`cap-only-reference-${i}`,objects:[object],lanes:5,scale:.5,fps:60,seed:41,capture:'encoded',reference_profile:'cap_only'}));
const acquired:RecordData[]=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-m','tests.play.skins.scenes'],{
 input:JSON.stringify([...scenes,...limited]),encoding:'utf8',maxBuffer:32*1024*1024}));

for(const scene of scenes)test(`encoded RGB -> real decoder -> tracks/roles/connections: ${scene.id}`,()=>{
 const r=acquired.find(r=>r.id===scene.id)!;
 assert.equal(r.source_preserved,true);assert.equal(r.frames.length,13);
 assert.deepEqual(r.frames.map(f=>f.pts),r.expected_source_pts,'original PTS agree with independent ffprobe frame integers');
 const endpoints=scene.objects.flatMap(o=>o.kind==='tap'?[{lane:o.lane,y:o.y,role:'tap'}]:[
  {lane:o.lane,y:o.y,role:'hold_start'},{lane:o.lane,y:o.end_y,role:'hold_end'}]);
 assert.equal(r.notes.length,endpoints.length);
 for(const [i,f]of r.frames.entries()){
  assert.equal(f.time,f.pts-42.125);assert.equal(f.caps.length,endpoints.length,'no clear-frame loss or extra cap');
  for(const e of endpoints){
   const expected=Math.round(e.y-80*i/scene.fps)*scene.scale;
   const found=f.caps.filter(c=>c.lane===e.lane&&Math.abs(c.y*300*scene.scale-expected)<1e-6);
   assert.equal(found.length,1);assert.equal(found[0].role,e.role);
  }
 }
 for(const e of endpoints){
  const i=r.notes.findIndex(n=>n.lane===e.lane&&Math.abs(n.points[0][1]-e.y*scene.scale)<1e-6);
  assert.ok(i>=0);assert.equal(r.notes[i].points.length,13);
  assert.equal(r.roles[i].status,e.role==='tap'?'tap':'hold');
  assert.deepEqual(r.roles[i].observations.map(o=>o.source_pts_seconds),r.expected_source_pts);
  assert.deepEqual(r.coordinates.notes[i].observations.map(o=>o.source_pts_seconds),r.expected_source_pts);
 }
 const holds=scene.objects.filter(o=>o.kind==='hold');
 assert.equal(r.connections.length,holds.length);
 for(const h of holds){
  const found=r.connections.filter(c=>c.lane===h.lane&&Math.abs(r.notes[c.head_note].points[0][1]-h.y*scene.scale)<1e-6&&
   Math.abs(r.notes[c.tail_note].points[0][1]-h.end_y*scene.scale)<1e-6);
  assert.equal(found.length,1);
  assert.deepEqual([...new Set(found[0].image_connection_evidence.map(p=>p.source_pts))],r.expected_source_pts);
 }
 assert.deepEqual(r.warnings,[]);
});

for(const scene of limited)test(`missing role references retain caps without inventing taps or holds: ${scene.id}`,()=>{
 const r=acquired.find(r=>r.id===scene.id)!;
 assert.equal(r.source_preserved,true);assert.equal(r.frames.length,13);
 assert.ok(r.frames.every(f=>f.caps.length===(scene.objects[0].kind==='tap'?1:2)));
 assert.ok(r.roles.every(n=>n.status==='unknown'));
 assert.deepEqual(r.connections,[]);
});
