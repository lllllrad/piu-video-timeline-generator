import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {imageHoldScene} from './fixtures.ts';
import {observedTailRoles} from '../../src/piu_timeline/derived/hold_projection.ts';

const root=fileURLToPath(new URL('../../',import.meta.url));
const script=`import json,sys
from copy import deepcopy
from piu_timeline.play.skins.holds import reconstruct_images
s=json.load(sys.stdin);before=deepcopy(s);warnings=[]
r=reconstruct_images(s['data'],[],s['native'],warnings,references=s['references'],cap_references=s['cap_references'],include_state=False)
print(json.dumps({**r,'warnings':warnings,'unchanged':s==before}))`;
function measure(s:ReturnType<typeof imageHoldScene>){
 return JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{cwd:root,input:JSON.stringify(s),encoding:'utf8'}));
}
function failClock(s:ReturnType<typeof imageHoldScene>,index=1){
 Object.assign(s.data.notes[index],{status:'excluded',target_seconds:null,reason:'shared_timing_reconstruction_failed',
  timing_reconstruction:{status:'failed',reason:'insufficient_or_inconsistent_shared_motion'}});
}
for(const scale of [.5,1,2])for(const fps of [25,50,100])test(`image topology survives a failed tail clock: scale=${scale}, fps=${fps}`,()=>{
 const s=imageHoldScene(scale,fps);failClock(s);
 const r=measure(s);assert.deepEqual(r.holds,[]);assert.equal(r.image_connections.length,1);assert.ok(r.unchanged);
 const c=r.image_connections[0];assert.deepEqual(c.covered_notes,[0,1]);
 assert.deepEqual([...new Set(c.image_connection_evidence.map(p=>p.source_pts))],s.native.map(f=>f.source_pts_seconds));
 assert.ok(!('start_range'in c));assert.ok(!('end_range'in c));
 const warning=r.warnings.find(w=>w.reason==='hold_endpoint_timing_unresolved');assert.ok(warning);
 assert.equal(warning.geometry_status,'connected');assert.equal(warning.image_connection_id,c.id);
});
test('two failed clocks or contradictory clock order cannot erase measured connectivity',()=>{
 for(const mode of ['both-failed','reversed']){
  const s=imageHoldScene();
  if(mode==='both-failed'){failClock(s,0);failClock(s,1);}else s.data.notes[1].target_seconds=.5;
  const r=measure(s);assert.equal(r.image_connections.length,1);assert.deepEqual(r.holds,[]);
  assert.ok(r.warnings.some(w=>w.reason==='hold_endpoint_timing_unresolved'));assert.ok(r.unchanged);
 }
});
test('failed clocks cannot turn disconnected image endpoints into a hold',()=>{
 const s=imageHoldScene();failClock(s);
 for(const frame of s.native)frame.skin_observations.pop();
 const r=measure(s);assert.deepEqual(r.image_connections,[]);assert.deepEqual(r.holds,[]);
 assert.ok(r.warnings.some(w=>w.reason==='unresolved_hold_geometry'));
});
test('an untimed interior tap still refutes a connected-body proposal',()=>{
 const s=imageHoldScene();failClock(s);const frame=s.native[3],time=frame.playback_seconds,y=130-100*time;
 frame.skin_observations.push({lane:0,x:.1,y:y/300,role:'tap',template:'tap',skin:'synthetic',region_errors:{cap:0},bounds_pixels:[10,y-10,30,y+10]});
 s.data.notes.push({lane:0,status:'excluded',target_seconds:null,points:[[time,y]]});
 const r=measure(s);assert.deepEqual(r.image_connections,[]);assert.deepEqual(r.holds,[]);
 assert.ok(r.warnings.some(w=>w.failure_detail==='skin_hold_interior_note_conflict'));
});

test('an untimed image connection retains tail ownership for downstream consumers',()=>{
 const s=imageHoldScene();failClock(s);const r=measure(s);
 const data={...s.data,hold_analysis:r,visual_channels:{note_types:{notes:s.data.notes.map((_,i)=>({note:i,
  observations:s.native.map(f=>({kind:'hold',role:i===0?'hold_start':'hold_end',playback_seconds:f.playback_seconds,source_pts_seconds:f.source_pts_seconds}))}))}}};
 const roles=observedTailRoles(data);assert.equal(roles.length,1);
 assert.equal(roles[0].tail_note,1);assert.equal(roles[0].head_note,0);assert.equal(roles[0].image_connection_id,0);
 assert.deepEqual(r.holds,[]);
});
