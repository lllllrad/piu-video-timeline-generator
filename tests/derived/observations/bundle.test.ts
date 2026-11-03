import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdtempSync,rmSync,readFileSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {frames,manifest,spatialMasks} from '../../../src/piu_timeline/derived/observations/bundle.ts';
import {createHash} from 'node:crypto';

const script=String.raw`
import json,sys
from hashlib import sha256
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import numpy as np
from piu_timeline.play.observations.bundle import acquire,read_manifest,FORMAT
root=Path(sys.argv[1]);media=root/'source.mkv';media.write_bytes(b'original source remains unchanged')
stat=media.stat()
layout={'receptor_y':.25,'note_y_max':.95,'combo_roi':[.3,.55,.2,.1],
 'judgment_roi':[.2,.35,.5,.15],'lanes':[{'x':.2+i*.13,'color':c}for i,c in enumerate(('blue','red','yellow','red','blue'))]}
data={'media':{'path':str(media),'size_bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns,'container_start_seconds':30},
 'layout':layout,'start_seconds':1,'end_seconds':3,'game_roi':[0,0,200,200]}
image=np.arange(200*200*3,dtype='uint8').reshape(200,200,3)
source=[(31+i*.017,1+i*.017,((image.astype('uint16')+i*7)%256).astype('uint8'))for i in range(66)]
with patch('piu_timeline.play.observations.bundle.decode_frames',return_value=iter(source)):
 saved=acquire(data,root/'bundle',width=200)
assert saved['frame_count']==66 and len(saved['chunks'])==2
with patch('piu_timeline.play.observations.bundle.decode_frames',side_effect=AssertionError('must reuse source-bound capture')):
 assert acquire(data,root/'bundle',width=200)==saved
read_manifest(root/'bundle',verify=True)
# Association, chart, grade and processing outcomes never invalidate acquisition.
changed=deepcopy(data);changed.update(matches=[{'note':999}],combo_events=[{'delta':10}],song='Different OCR title')
with patch('piu_timeline.play.observations.bundle.decode_frames',side_effect=AssertionError('consumer fields must not decode')):
 assert acquire(changed,root/'bundle',width=200)==saved
from piu_timeline.play.observations.bundle import crop
(root/'expected.json').write_text(json.dumps({
 'game':[sha256(f[2].tobytes()).hexdigest()for f in source],
 'input':[sha256(crop(f[2],saved['geometry']['input']).tobytes()).hexdigest()for f in source],
 'popup':[sha256(crop(f[2],saved['geometry']['popup']).tobytes()).hexdigest()for f in source]}))
original=(root/'bundle/manifest.json').read_bytes()
# Failed acquisition preserves the published artifact and removes only its own staging tree.
changed=deepcopy(data);changed['game_roi'][0]=1
with patch('piu_timeline.play.observations.bundle.decode_frames',return_value=iter([source[0],source[0]])):
 try:acquire(changed,root/'bundle',width=200)
 except ValueError:pass
 else:raise AssertionError('duplicate PTS accepted')
assert (root/'bundle/manifest.json').read_bytes()==original
assert not list(root.glob('.*.build'))
# Geometry interpretation changes do not require another original-media decode.
changed=deepcopy(data);changed['layout']['receptor_y']=.26
with patch('piu_timeline.play.observations.bundle.decode_frames',side_effect=AssertionError('layout changes reuse complete game RGB')):
 assert acquire(changed,root/'bundle',width=200)['contract']['source']['layout']['receptor_y']==.26
 acquire(data,root/'bundle',width=200)
assert (root/'bundle/manifest.json').read_bytes()==original
# A new detector reuses lossless pixels, preserving overlapping hypotheses independently.
class Detector:
 contract={'method':'synthetic_code','revision':1}
 def candidates(self,rgb):
  assert rgb.shape==image.shape
  return [{'lane':0,'x':.2,'y':.6,'role':role,'method':'synthetic_code','bounds_pixels':[30,110,50,130]}
          for role in ('tap','hold_start','hold_end')]
with patch('piu_timeline.play.observations.bundle.decode_frames',side_effect=AssertionError('detector changes must reuse RGB')):
 acquire(data,root/'bundle',width=200,detector=Detector())
class FailedDetector:
 contract={'method':'synthetic_code','revision':2}
 def candidates(self,rgb):raise ValueError('deliberate detector failure')
with patch('piu_timeline.play.observations.bundle.decode_frames',side_effect=AssertionError('failed detector must not reacquire pixels')):
 try:acquire(data,root/'bundle',width=200,detector=FailedDetector())
 except ValueError:pass
 else:raise AssertionError('failed detector was accepted')
read_manifest(root/'bundle',verify=True)
assert (root/'bundle/manifest.json').read_bytes()==original
print(json.dumps({'frames':66,'source':str(media),'original':list(image[50:103].tobytes()[:8])}))
`;
function fixture(){
 const root=mkdtempSync(join(tmpdir(),'independent-channels-'));
 try{
  execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script,root],{encoding:'utf8'});
  return root;
 }catch(error){rmSync(root,{recursive:true,force:true});throw error;}
}

test('channels preserve exact source PTS, original RGB and complete full-field mask frames across chunks',()=>{
 const root=fixture();try{
  const path=join(root,'bundle'),saved=manifest(path),observed=[...frames(path,{pixels:true,gamePixels:true})];
  assert.equal(saved.channels.notes.status,'available');assert.equal(saved.channels.popup.status,'available');
  assert.equal(observed.length,66);
  assert.deepEqual(observed[0].note_candidates.map(c=>c.role),['tap','hold_start','hold_end']);
  assert.deepEqual(observed[0].note_candidates.map(c=>c.candidate),[0,1,2]);assert.equal(observed[65].frame,65);
  assert.equal(observed[65].source_pts_seconds,31+65*.017);
  assert.equal(observed[65].playback_seconds,1+65*.017);
  const expected=JSON.parse(readFileSync(join(root,'expected.json'),'utf8'));
  for(const frame of observed)for(const key of ['game','input','popup'])assert.equal(createHash('sha256').update(frame[key+'_rgb']).digest('hex'),expected[key][frame.frame]);
  assert.equal(observed[0].input_rgb.length,(saved.geometry.input[3]-saved.geometry.input[1])*200*3);
  const masks=[...spatialMasks(path)];assert.equal(masks.length,66);assert.equal(masks[65].frame,65);
 }finally{rmSync(root,{recursive:true,force:true});}
});
test('independent channel reads ignore unrelated damaged channels but reject corruption in their own evidence',()=>{
 const root=fixture();try{
  const path=join(root,'bundle'),saved=manifest(path);
  const notes=Object.keys(saved.notes_stage.chunks[0].files).find(n=>n.endsWith('.notes.jsonl.gz'));
  const bytes=readFileSync(join(path,'notes',notes));bytes[bytes.length-5]^=1;writeFileSync(join(path,'notes',notes),bytes);
  assert.equal([...frames(path,{channel:'input'})].length,66);
  assert.equal([...frames(path,{channel:'timeline'})].length,66);
  assert.throws(()=>[...frames(path,{channel:'notes'})],/Corrupt/);
  writeFileSync(join(path,'notes/manifest.json'),'broken note metadata');
  assert.equal([...frames(path,{channel:'input',pixels:true})].length,66);
  assert.equal([...spatialMasks(path)].length,66);
  writeFileSync(join(root,'source.mkv'),'changed original identity');
  assert.throws(()=>manifest(path),/source changed/);
 }finally{rmSync(root,{recursive:true,force:true});}
});
