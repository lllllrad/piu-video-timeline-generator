import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import type {RecordData} from '../../src/piu_timeline/derived/types.ts';

interface ObjectTruth {kind:'tap'|'hold';lane:number;y:number;end_y?:number}
interface Scene {id:string;cases:string[];objects:ObjectTruth[];lanes:number;scale:number;fps:number;seed:number;mode?:string}
const tap=(lane:number,y=80):ObjectTruth=>({kind:'tap',lane,y});
const hold=(lane:number,y=80,end_y=160):ObjectTruth=>({kind:'hold',lane,y,end_y});
const basic:[string,string[],ObjectTruth[],number][]=[
 ['empty',['O01'],[],5],
 ...Array.from({length:5},(_,i):[string,string[],ObjectTruth[],number]=>[`isolated-lane${i}`,['O02'],[tap(i)],5]),
 ['single-chord',['O03'],Array.from({length:5},(_,i)=>tap(i)),5],
 ['double-chord',['O03'],Array.from({length:10},(_,i)=>tap(i)),10],
 ['stagger',['O04'],[tap(0),tap(1,86),tap(2,92)],5],
 ['repeated',['O05'],[80,120,160,200].map(y=>tap(0,y)),5],
 ['long-hold',['O06','O10'],[hold(1)],5],
 ['short-hold',['O07','O10'],[hold(2,80,106)],5],
 ['two-short-spaced-taps',['O08'],[tap(2,80),tap(2,106)],5],
 ['adjacent-holds',['O11'],[hold(0,80,106),hold(0,140,166)],5],
 ['tap-before-hold',['O12'],[tap(3,80),hold(3,120,200)],5],
 ['tap-after-hold',['O12'],[hold(4,80,160),tap(4,200)],5],
 ['overlapping-lanes',['O13'],[hold(0),tap(1,100),hold(7,90,170)],10],
];
const scenes:Scene[]=basic.flatMap(([name,cases,objects,lanes],i)=>[.5,1,1.5,2].map((scale,j)=>({
 id:`${name}-scale${scale}`,cases,objects,lanes,scale,fps:[30,60,120][(i+j)%3],seed:100+i*7+j})));
for(const scale of [1.25,4/3])for(const [name,cases,objects,lanes]of basic.filter(b=>['short-hold','two-short-spaced-taps','adjacent-holds'].includes(b[0])))
 scenes.push({id:`${name}-scale${scale}`,cases:[...cases,'T05'],objects,lanes,scale,fps:60,seed:41});
const uncertain:Scene[]=['opaque_connection','body_only','contradictory_roles'].flatMap((mode,i)=>[.5,1,1.5,2].map(scale=>({
 id:`${mode}-scale${scale}`,cases:[['O15','O17','O16'][i]],objects:[hold(2)],lanes:5,scale,fps:60,seed:700+i,mode})));
const acquired:RecordData[]=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-m','tests.play.skins.scenes'],{
 input:JSON.stringify([...scenes,...uncertain]),encoding:'utf8',maxBuffer:32*1024*1024}));

for(const scene of scenes)test(`${scene.cases.join('/')} native RGB -> tracks -> image connections: ${scene.id}`,()=>{
 const result=acquired.find(r=>r.id===scene.id)!;
 assert.ok(result);
 const endpoints=scene.objects.flatMap(o=>o.kind==='tap'?[{lane:o.lane,y:o.y,role:'tap'}]:[
  {lane:o.lane,y:o.y,role:'hold_start'},{lane:o.lane,y:o.end_y!,role:'hold_end'}]);
 assert.equal(result.notes.length,endpoints.length,'exact native cap-track count');
 if(scene.id==='isolated-lane0-scale0.5')assert.ok(result.cap_subfeature_frames>0,'body-pattern matches inside cap art retain their explicit explanation');
 for(const frame of result.frames){
  assert.equal(frame.pts,42.125+frame.time);
  assert.equal(frame.caps.length,endpoints.length,'no missing or extra cap in a clear frame');
  for(const e of endpoints){
   const expectedY=Math.round(e.y-80*frame.time)*scene.scale;
   const matches=frame.caps.filter(c=>c.lane===e.lane&&Math.abs(c.y*300*scene.scale-expectedY)<1e-5);
   assert.equal(matches.length,1,`one ${e.role} in lane ${e.lane} at ${frame.time}`);
   assert.equal(matches[0].role,e.role);
  }
 }
 assert.equal(result.roles.length,endpoints.length);
 for(const e of endpoints){
  const index=result.notes.findIndex(n=>n.lane===e.lane&&Math.abs(n.points[0][1]-e.y*scene.scale)<1e-5);
  assert.ok(index>=0,'acquired track starts at this independently specified cap');
  const points=result.notes[index].points;
  assert.equal(points.length,result.frames.length,'identity must persist through every clear captured frame');
  points.forEach(([time,y],i)=>{
   assert.equal(time,result.frames[i].time);
   // Normalized image coordinates can round-trip a raster integer as 79-epsilon.
   assert.ok(Math.abs(y-Math.round(e.y-80*time)*scene.scale)<1e-8);
  });
  assert.equal(result.roles[index].status,e.role==='tap'?'tap':'hold');
  assert.deepEqual(result.coordinates.notes[index].observations.map(o=>[o.time,o.source_pts_seconds]),
   result.frames.map(f=>[f.time,f.pts]),'native coordinate measurement retains every acquired source frame');
  assert.deepEqual(result.roles[index].observations.map(o=>[o.playback_seconds,o.source_pts_seconds,o.role]),
   result.frames.map(f=>[f.time,f.pts,e.role]),'role join preserves original per-frame provenance');
 }
 const holds=scene.objects.filter(o=>o.kind==='hold');
 assert.equal(result.connections.length,holds.length,'one image object per hold, no tail tap or spanning hold');
 for(const obj of holds){
  const candidates=result.connections.filter(h=>{
   const head=result.notes[h.head_note],tail=result.notes[h.tail_note];
   return h.lane===obj.lane&&Math.abs(head.points[0][1]-obj.y*scene.scale)<1e-5&&Math.abs(tail.points[0][1]-obj.end_y!*scene.scale)<1e-5;
  });
  assert.equal(candidates.length,1,'independently acquired endpoints match this hold');
 }
 assert.deepEqual(result.warnings,[],'fully visible ordinary geometry must not remain unresolved');
});

for(const scene of uncertain)test(`native RGB keeps insufficient/contradictory geometry explicit: ${scene.id}`,()=>{
 const r=acquired.find(r=>r.id===scene.id)!;
 assert.equal(r.connections.length,0);
 assert.ok(r.frames.every(f=>f.pts===42.125+f.time));
 if(scene.mode==='body_only'){
  assert.deepEqual(r.notes,[],'a body cannot create endpoint tracks');
  assert.ok(r.warnings.some(w=>w.failure_detail==='skin_body_images_without_complete_endpoint_ownership'));
 }else{
  assert.equal(r.notes.length,2,'retain both observed cap identities');
  const status=scene.mode==='opaque_connection'?'unknown':'conflict';
  assert.deepEqual(r.roles.map(n=>n.status),[status,status]);
  if(status==='conflict'){
   assert.ok(r.warnings.length>0);
   assert.ok(r.roles.every(n=>n.observations.some(o=>o.role==='tap')));
   assert.ok(r.roles.every(n=>n.observations.some(o=>['hold_start','hold_end'].includes(o.role))));
  }
 }
});
