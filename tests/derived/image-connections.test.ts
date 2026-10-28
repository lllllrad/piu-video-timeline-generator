import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {imageHoldScene,adjacentImageHolds} from './fixtures.ts';
import {project as timeConnections} from '../../src/piu_timeline/derived/holds/image_timing.ts';
import {observedTailRoles} from '../../src/piu_timeline/derived/hold_projection.ts';

const root=fileURLToPath(new URL('../../',import.meta.url));
const script=`import json,sys
from copy import deepcopy
from piu_timeline.play.skins.holds import measure_connections
s=json.load(sys.stdin);before=deepcopy(s);warnings=[]
c=measure_connections(s['data'],s['native'],warnings,references=s['references'],cap_references=s['cap_references'])
print(json.dumps({'image_connections':c,'unresolved_tracks':warnings,'unchanged':s==before}))`;
function measure(s:ReturnType<typeof imageHoldScene>):ReturnType<typeof timeConnections>{
 const geometry=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{cwd:root,input:JSON.stringify(s),encoding:'utf8'}));
 const before=structuredClone(s.data.notes),result=timeConnections(s.data.notes,geometry);
 assert.deepEqual(s.data.notes,before);return {...result,warnings:result.unresolved_tracks};
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
test('a proven body cannot shorten the warning span of later unverified endpoint observations',()=>{
 const s=imageHoldScene();failClock(s);const frame=structuredClone(s.native.at(-1)),time=.25;
 frame.playback_seconds=time;frame.source_pts_seconds=80+time;frame.skin_observations=frame.skin_observations.slice(0,2);
 for(const [i,image]of frame.skin_observations.entries()){
  const y=100-100*time+60*i,delta=y-image.y*300;image.y=y/300;
  image.bounds_pixels=image.bounds_pixels.map((v,j)=>j%2?v+delta:v);image.role='unknown';image.classification_status='cap_only';
  s.data.notes[i].points.push([time,y]);
 }
 s.native.push(frame);const r=measure(s);assert.equal(r.image_connections.length,1);assert.deepEqual(r.holds,[]);
 const warning=r.warnings.find(w=>w.reason==='hold_endpoint_timing_unresolved');
 assert.equal(warning.visible_end_seconds,time);
 assert.ok(r.image_connections[0].source_pts_range[1]<80+time,'the later cap is not fabricated body evidence');
});
test('clock changes reuse native image measurement while refreshing timed intervals',()=>{
 const s=imageHoldScene();failClock(s);s.data.media={path:'synthetic',size_bytes:0,mtime_ns:0};
 const script=`import json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
from piu_timeline.play.holds.stages import geometry
from piu_timeline.play.skins.holds import measure_connections
s=json.load(sys.stdin)
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);(root/'frames.jsonl').write_text(''.join(json.dumps(f)+'\\n'for f in s['native']))
 with patch('piu_timeline.play.skins.coverage.reference_rows',side_effect=lambda data,cap_only=False:s['cap_references']if cap_only else s['references']),patch('piu_timeline.play.skins.holds.measure_connections',wraps=measure_connections)as measured:
  first=geometry(s['data'],root,s['native'],None);before=json.loads((root/'native-stages/hold-geometry.json').read_text())
  n=s['data']['notes'][1];n.update(status='estimated',reason=None,target_seconds=1.45,timing_reconstruction={'status':'restored'})
  second=geometry(s['data'],root,s['native'],None)
  frames=json.loads(json.dumps(s['native']));frames[0]['bodies']=[{'other_channel':True}]
  third=geometry(s['data'],root,frames,None);after=json.loads((root/'native-stages/hold-geometry.json').read_text())
  print(json.dumps({'first':first,'second':second,'measurements':measured.call_count,'physical_cache_unchanged':before==after,'physical_keys':list(after['output'])}))`;
 const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{cwd:root,input:JSON.stringify(s),encoding:'utf8'}));
 assert.equal(r.measurements,1);assert.ok(r.physical_cache_unchanged);assert.ok(!r.physical_keys.includes('holds'));
 assert.deepEqual(r.first.holds,[]);assert.equal(r.second.holds.length,1);
 assert.deepEqual(r.second.holds[0].end_range,[1.44,1.46]);
 assert.ok(!r.second.unresolved_tracks.some(w=>w.reason==='hold_endpoint_timing_unresolved'));
});

for(const scale of [.5,1,2])for(const fps of [25,50,100])test(`interior hold caps separate adjacent source objects: scale=${scale}, fps=${fps}`,()=>{
 const s=adjacentImageHolds(scale,fps),r=measure(s);
 assert.deepEqual(r.image_connections.map(c=>[c.head_note,c.tail_note]),[[0,1],[2,3]]);
 assert.deepEqual(r.holds.map(h=>[h.head_note,h.tail_note]),[[0,1],[2,3]]);
 assert.deepEqual(r.warnings,[]);assert.ok(r.unchanged);
});
test('an untimed adjacent cap still refutes a spanning hold candidate',()=>{
 const s=adjacentImageHolds();failClock(s,0);const r=measure(s);
 assert.deepEqual(r.image_connections.map(c=>[c.head_note,c.tail_note]),[[0,1],[2,3]]);
 assert.deepEqual(r.holds.map(h=>[h.head_note,h.tail_note]),[[2,3]]);
 assert.equal(r.warnings.filter(w=>w.reason==='hold_endpoint_timing_unresolved').length,1);
 assert.ok(!r.warnings.some(w=>w.failure_detail==='skin_hold_interior_note_conflict'));
});
