import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';
import {resolve}from '../../../src/piu_timeline/derived/skins/localization.ts';
const samples=Array.from({length:4},(_,i)=>{
 const y=200-i,time=i/60;
 const measurement=resolve({height:400,raw_y:y,comparisons:[{template:'cap',comparison_index:0,image_y:y/400,
  cap_error:0,maximum_error:.015,scale_y:1,same_cap:true,center_offset_y_pixels:0,reference:'reference',
  localization_pixels:{method:'visible_cap_rgb_and_vertical_contrast',compared_pixels:400,
   vertical_contrast_pixels:80,squared_rgb_error:0,vertical_contrast_error:0}}]}).measurement;
 return {...measurement,time,source_pts_seconds:80+time,detected_y_pixels:y,template:'cap',
  cap_reference_sha256:'reference',classification_status:'full_pattern'};
});
const script=String.raw`
import json,tempfile,sys
from pathlib import Path
from piu_timeline.derived import CONTRACTS
from piu_timeline.play.stages import fingerprint
from piu_timeline.play.observations.tracking import retained
samples=json.load(sys.stdin)
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);layout={'lanes':[{'x':.1},{'x':.2}],'receptor_y':.1}
 data={'media':{'path':'source.mkv','mtime_ns':1790000000000000001},'game_roi':[0,0,400,400],
  'analysis_width':400,'analysis_height':400,'layout':layout,'start_seconds':0,'end_seconds':1,'frame_count':4,
  'skin_detector':{'contract':{'bank':'generated-bank'}}}
 binding={'source':{k:data[k]for k in ('media','game_roi','start_seconds','end_seconds')},
  'geometry':{'width':400,'height':400,'layout':layout},'detector_contract':data['skin_detector']['contract'],
  'coordinate_contract':CONTRACTS['image_coordinates'],'frame_observations_sha256':'source-frame-digest'}
 original={'input':binding,'input_fingerprint':fingerprint(binding),
  'timeline':[{'time':s['time'],'source_pts':s['source_pts_seconds']}for s in samples],
  'notes':[{'lane':0,'points':[[s['time'],s['detected_y_pixels']]for s in samples],
   'coordinate_measurements':samples,'target_seconds':999,'previous_owner':123,'status':'estimated'}]}
 path=root/'tracking.json';path.write_text(json.dumps(original));before=path.read_bytes()
 bank={'templates':[{'id':'cap','role':'hold_start'}]}
 first=retained(data,root,bank);second=retained(data,root,bank)
 changed=retained({**data,'analysis_width':800},root,bank)
 cache=root/'tracking-observations.json';bad=json.loads(cache.read_text());bad['frames'][0]['time']=99
 cache.write_text(json.dumps(bad))
 try:retained(data,root,bank);corrupt=False
 except ValueError:corrupt=True
 print(json.dumps({'first':first,'repeat':first['frames']==second['frames'],
  'original_unchanged':path.read_bytes()==before,'geometry_mismatch':changed,'corrupt_rejected':corrupt}))
`;
test('saved per-frame positions discard previous identities, preserve source PTS and reject changed acquisition',()=>{
 const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{
  input:JSON.stringify(samples),encoding:'utf8',maxBuffer:4*1024*1024}));
 assert.equal(r.repeat,true);assert.equal(r.original_unchanged,true);assert.equal(r.geometry_mismatch,null);assert.equal(r.corrupt_rejected,true);
 assert.equal(r.first.frames.length,4);
 for(const [i,frame]of r.first.frames.entries()){
  assert.equal(frame.time,i/60);assert.equal(frame.source_pts,80+i/60);
  assert.equal(frame.observations[0].center.yPixels,200-i);
  assert.equal(frame.observations[0].center.uncertaintyPixels,0);
  assert.equal(frame.observations[0].capRole,'hold_start');
 }
 for(const field of ['target_seconds','previous_owner','estimated'])assert.ok(!JSON.stringify(r.first).includes(field));
});
