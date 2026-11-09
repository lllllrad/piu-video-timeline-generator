import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {occludedHold} from './occlusion-fixtures.ts';
const script=String.raw`
import json,sys
from piu_timeline.play.skins.holds import measure_connections
from piu_timeline.derived import call
s=json.load(sys.stdin);warnings=[]
c=measure_connections(s['data'],s['native'],warnings,references=s['references'],cap_references=s['cap_references'])
print(json.dumps(call('holdImages.project',s['data']['notes'],{'image_connections':c,'unresolved_tracks':warnings})))`;
function measure(s:ReturnType<typeof occludedHold>){return JSON.parse(execFileSync('sh',
 ['scripts/run.sh','.venv/bin/python','-c',script],{input:JSON.stringify(s),encoding:'utf8'}));}
for(const scale of [.5,1,2])for(const fps of [30,60,120])test(`known HUD connects visible hold portions without inventing pixels: scale=${scale}, fps=${fps}`,()=>{
 const s=occludedHold(scale,fps),before=structuredClone(s),r=measure(s);
 assert.equal(r.holds.length,1);assert.deepEqual(r.holds[0].covered_notes,[0,1]);assert.deepEqual(s,before);
 const proof=r.holds[0].image_connection_evidence.filter(p=>p.occluded_intervals);
 assert.equal(proof.length,4);
 for(const p of proof){
  assert.ok(p.occluded_intervals.every(g=>g.region==='judgment_word'&&g.bounds_pixels[0]>=120*scale&&g.bounds_pixels[1]<=195*scale));
  assert.ok(p.observed_intervals_pixels.every(([a,b])=>b<=120*scale||a>=195*scale));
 }
 assert.equal(r.holds[0].source_pts_range[0],80);assert.equal(r.holds[0].source_pts_range[1],80+3/fps);
});
test('visible gaps, wrong lanes, missing endpoints and ambiguous ownership cannot be excused by a nearby HUD',()=>{
 for(const mode of ['visible-gap','wrong-lane','absent-endpoint','competing-tail','stationary','capture-gap']){
  const s=occludedHold();
  if(mode==='visible-gap')for(const f of s.native)f.skin_observations=f.skin_observations.filter(o=>o.role!=='hold_body'||o.bounds_pixels[3]<=108||o.bounds_pixels[1]>=119);
  if(mode==='wrong-lane')s.data.layout.judgment_roi[0]=.4;
  if(mode==='absent-endpoint')s.data.notes[1].points=[];
  if(mode==='competing-tail')s.data.notes.push(structuredClone(s.data.notes[1]));
  if(mode==='stationary'){
   for(const n of s.data.notes)n.points.forEach(p=>p[1]=n.points[0][1]);
   s.native.forEach((f,i)=>{f.skin_observations=structuredClone(s.native[0].skin_observations);});
  }
  if(mode==='capture-gap'){
   s.native.forEach((f,i)=>{f.playback_seconds=i*.1;f.source_pts_seconds=80+i*.1;});
   s.data.notes.forEach(n=>n.points.forEach((p,i)=>p[0]=i*.1));
  }
  const r=measure(s);assert.deepEqual(r.holds,[],mode);assert.ok(r.unresolved_tracks.length,mode);
 }
});
test('a positively observed tap refutes an occlusion-covered connection',()=>{
 const s=occludedHold(),f=s.native[1],y=160;
 f.skin_observations.push({lane:0,x:.1,y:y/300,role:'tap',template:'tap',skin:'synthetic',classification_status:'full_pattern',
  region_errors:{cap:0},bounds_pixels:[10,y-10,30,y+10]});
 s.data.notes.push({lane:0,points:[[f.playback_seconds,y]],status:'excluded',target_seconds:null});
 const r=measure(s);assert.deepEqual(r.holds,[]);assert.ok(r.unresolved_tracks.some(w=>w.failure_detail==='skin_hold_interior_note_conflict'));
});
test('a repeated rendered image at a distinct source PTS does not erase a moving rigid hold',()=>{
 const s=occludedHold();s.native[2].skin_observations=structuredClone(s.native[1].skin_observations);
 s.data.notes.forEach(n=>n.points[2][1]=n.points[1][1]);
 const r=measure(s);assert.equal(r.holds.length,1);
 assert.ok(r.holds[0].image_connection_evidence.some(p=>p.source_pts===s.native[2].source_pts_seconds));
});
test('a proven pair retains the original late tail/body observations after its head has reached the receptor',()=>{
 const s=occludedHold(1,60,true),r=measure(s);assert.equal(r.holds.length,1);
 const last=s.native.at(-1),late=r.holds[0].image_connection_evidence.filter(p=>p.time===last.playback_seconds);
 assert.ok(late.some(p=>p.tail_y===60&&p.body_template_support));
 assert.ok(late.every(p=>!('head_y'in p)),'no head position is invented after consumption');
 assert.equal(r.holds[0].source_pts_range[1],last.source_pts_seconds);
});
test('image connectivity survives a failed clock and does not manufacture an endpoint time',()=>{
 const s=occludedHold();Object.assign(s.data.notes[0],{status:'excluded',target_seconds:null,
  timing_reconstruction:{status:'failed'},reason:'shared_timing_reconstruction_failed'});
 const r=measure(s);assert.equal(r.image_connections.length,1);assert.deepEqual(r.holds,[]);
 assert.equal(r.observed_holds.length,1);assert.equal(r.observed_holds[0].geometry_status,'connected');
 assert.equal(r.observed_holds[0].timing_status,'unresolved');assert.equal(r.observed_holds[0].start_range,null);
 assert.equal(r.observed_holds[0].head_note,0);assert.equal(r.observed_holds[0].tail_note,1);
 assert.equal(r.observed_holds[0].requires_head_press,false);
 assert.ok(r.unresolved_tracks.some(w=>w.reason==='hold_endpoint_timing_unresolved'));
});

const nativeScript=String.raw`
import json,tempfile
from pathlib import Path
from tests.play.skins.test_temporal import fixture
from piu_timeline.play.skins.holds import measure_connections
with tempfile.TemporaryDirectory()as tmp:
 data,frames,_=fixture(Path(tmp),hud=True)
 warnings=[];connections=measure_connections(data,frames,warnings)
 print(json.dumps({'connections':connections,'warnings':warnings,
  'coobserved':sorted(set(dict(data['notes'][0]['points']))&set(dict(data['notes'][1]['points'])))}))`;
test('a hold longer than the field crosses a known HUD using real synthetic RGB comparisons',()=>{
 const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',nativeScript],{encoding:'utf8'}));
 assert.deepEqual(r.coobserved,[]);assert.equal(r.connections.length,1);
 const c=r.connections[0];assert.deepEqual(c.covered_notes,[0,1]);
 const links=c.image_connection_evidence.flatMap(p=>p.occlusion_links??[]);assert.ok(links.length>0);
 assert.ok(links.every(l=>l.occluded_intervals.every(g=>g.region==='judgment_word'&&g.bounds_pixels[0]>=120&&g.bounds_pixels[1]<=195)));
 assert.ok(c.image_connection_evidence.every(p=>p.covered_bounds_pixels[1]<=120||p.covered_bounds_pixels[0]>=195),
  'the known hidden rows remain absent from all positive pixel intervals');
});

const clearanceScript=String.raw`
import json,tempfile
from pathlib import Path
import numpy as np
from tests.play.skins.test_detector import examples
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.observations import observe
results=[]
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);items,_=examples(root);bank=load_bank(root/'bank.json')
 for rect in [[.05,115/300,.1,10/300],[.05,132/300,.1,8/300]]:
  layout={'receptor_y':.05,'combo_roi':[.7,.8,.14,.075],'judgment_roi':rect,'lanes':[{'x':.1+i*.1}for i in range(5)]}
  image=np.zeros((300,200,3),dtype='uint8');image[100:140,10:30]=items[0][1]
  detected=SkinDetector(bank,layout,200,300).detect(image)
  frame={'playback_seconds':1.,'source_pts_seconds':41.,'skin_observations':detected}
  data={'analysis_width':200,'analysis_height':300,'layout':layout,'notes':[{'lane':0,'points':[[1.,120.]]}],
   'skin_detector':{'bank_path':str(root/'bank.json'),'contract':{'bank':bank['contract']}}}
  results.append({'native':next(o for o in detected if o['lane']==0 and abs(o['y']*300-120)<1e-6),
                  'interpreted':observe(data,[frame])['notes'][0]})
print(json.dumps(results))`;
test('positive cap matches survive HUD overlap, while hidden clearance cannot prove a tap',()=>{
 const [capOnlyOverlap,hiddenClearance]=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',clearanceScript],{encoding:'utf8'}));
 for(const c of [capOnlyOverlap,hiddenClearance])assert.equal(c.native.role,'tap','the original positive image comparison is retained');
 assert.equal(capOnlyOverlap.interpreted.status,'tap','the negative margins remain outside the foreground');
 assert.equal(hiddenClearance.interpreted.status,'unknown');
 const proof=hiddenClearance.interpreted.observations[0];assert.equal(proof.reason,'skin_tap_clearance_occluded');
 assert.deepEqual(proof.occluded_clearance_regions,['clear_below']);assert.equal(proof.comparison_classification_status,'full_pattern');
});
