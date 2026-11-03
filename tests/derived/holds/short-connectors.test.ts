import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {imageHoldScene} from '../fixtures.ts';

/** Positive endpoint connectors, with the other cap obscured in each frame. */
function shortHold(scale:number,fps:number){
 const s=imageHoldScene(scale,fps),split=Math.floor(s.native.length/2);
 s.data.notes.forEach(n=>n.points=[]);
 s.data.scroll_motion={samples:s.native.map((f,i)=>({time:f.playback_seconds,source_pts:f.source_pts_seconds,
  phase:200*scale*f.playback_seconds,chunk:0,support:i?2:0,coordinate_status:'joint_registered'}))};
 s.native.forEach((f,i)=>{
  const tail=i>=split,role=tail?'hold_end':'hold_start',y=(100-200*f.playback_seconds+(tail?20:0))*scale;
  f.skin_observations=[{lane:0,x:.1,y:y/(300*scale),role,template:role,skin:'synthetic',
   classification_status:'full_pattern',region_errors:{cap:0,connection:0},
   bounds_pixels:[10*scale,y-(tail?25:10)*scale,30*scale,y+(tail?10:25)*scale]}];
  s.data.notes[tail?1:0].points.push([f.playback_seconds,y]);
 });
 return {...s,body_references:{hold_start:[[20*scale,35*scale]],hold_end:[[0,15*scale]],hold_body:[]}};
}
const script=String.raw`
import json,sys
from piu_timeline.play.skins.holds import measure_connections
s=json.load(sys.stdin);warnings=[]
connections=measure_connections(s['data'],s['native'],warnings,references=s['references'],
 cap_references=s['cap_references'],body_references=s['body_references'])
print(json.dumps({'connections':connections,'warnings':warnings}))`;
function measure(s:ReturnType<typeof shortHold>){
 return JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{input:JSON.stringify(s),encoding:'utf8'}));
}
for(const scale of [.5,1,2])for(const fps of [25,50,100])test(`short hold connectors survive alternating cap visibility: scale=${scale}, fps=${fps}`,()=>{
 const s=shortHold(scale,fps),before=structuredClone(s),r=measure(s);
 assert.equal(r.connections.length,1);assert.deepEqual(s,before);
 const c=r.connections[0];assert.deepEqual(c.covered_notes,[0,1]);
 assert.equal(c.body_evidence,'skin_temporal_image_regions');
 assert.equal(c.body_frames,s.native.length);
 assert.ok(c.image_connection_evidence.every(p=>p.body_template_support));
 assert.ok(c.image_connection_evidence.every(p=>!('head_y'in p&&'tail_y'in p)));
 assert.deepEqual(c.source_pts_range,[s.native[0].source_pts_seconds,s.native.at(-1).source_pts_seconds]);
});
test('cap pixels, failed connector comparisons and missing frames cannot substitute for positive connector support',()=>{
 for(const mode of ['no-connector','failed-connector','missing-frame','missing-motion']){
  const s=shortHold(1,50);
  if(mode==='no-connector')s.body_references={hold_start:[],hold_end:[],hold_body:[]};
  if(mode==='failed-connector')s.native.forEach(f=>f.skin_observations[0].classification_status='cap_only');
  if(mode==='missing-frame')s.native[Math.floor(s.native.length/2)].skin_observations=[];
  if(mode==='missing-motion')s.data.scroll_motion.samples[Math.floor(s.native.length/2)].coordinate_status='failed';
  const r=measure(s);assert.deepEqual(r.connections,[],mode);assert.ok(r.warnings.length,mode);
 }
});
