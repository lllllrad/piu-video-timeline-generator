import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdtempSync,rmSync,readFileSync,writeFileSync,readdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {frames,manifest,spatialMasks} from '../../../src/piu_timeline/derived/observations/bundle.ts';

const script=String.raw`
import json,sys
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import numpy as np
from piu_timeline.play.observations.bundle import acquire,read_manifest
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
original=(root/'bundle/manifest.json').read_bytes()
# Failed acquisition preserves the published artifact and removes only its own staging tree.
changed=deepcopy(data);changed['game_roi'][0]=1
with patch('piu_timeline.play.observations.bundle.decode_frames',return_value=iter([source[0],source[0]])):
 try:acquire(changed,root/'bundle',width=200)
 except ValueError:pass
 else:raise AssertionError('duplicate PTS accepted')
assert (root/'bundle/manifest.json').read_bytes()==original
assert not list(root.glob('.*.build'))
# Geometry changes reacquire masks from the unchanged source recording.
changed=deepcopy(data);changed['layout']['receptor_y']=.26
with patch('piu_timeline.play.observations.bundle.decode_frames',return_value=iter(source)):
 assert acquire(changed,root/'bundle',width=200)['contract']['source']['layout']['receptor_y']==.26
with patch('piu_timeline.play.observations.bundle.decode_frames',return_value=iter(source)):
 acquire(data,root/'bundle',width=200)
assert (root/'bundle/manifest.json').read_bytes()==original
# A changed detector reads original frames; retained detections need no RGB cache.
class Detector:
 contract={'method':'synthetic_code','revision':1}
 def candidates(self,rgb):
  assert rgb.shape==image.shape
  return [{'lane':0,'x':.2,'y':.6,'role':role,'method':'synthetic_code','bounds_pixels':[30,110,50,130]}
          for role in ('tap','hold_start','hold_end')]
with patch('piu_timeline.play.observations.notes.decode_frames',return_value=iter(source)):
 acquire(data,root/'bundle',width=200,detector=Detector())
with patch('piu_timeline.play.observations.notes.decode_frames',side_effect=AssertionError('unchanged detector must reuse observations')):
 acquire(data,root/'bundle',width=200,detector=Detector())
class FailedDetector:
 contract={'method':'synthetic_code','revision':2}
 def candidates(self,rgb):raise ValueError('deliberate detector failure')
with patch('piu_timeline.play.observations.notes.decode_frames',return_value=iter(source)):
 try:acquire(data,root/'bundle',width=200,detector=FailedDetector())
 except ValueError:pass
 else:raise AssertionError('failed detector was accepted')
# Re-decoding must reproduce every original frame timestamp, not just the count.
prior_notes=(root/'bundle/notes/manifest.json').read_bytes()
Detector.contract={'method':'synthetic_code','revision':3}
shifted=[(pts+.002,time+.002,rgb)for pts,time,rgb in source]
with patch('piu_timeline.play.observations.notes.decode_frames',return_value=iter(shifted)):
 try:acquire(data,root/'bundle',width=200,detector=Detector())
 except ValueError as error:assert 'original PTS'in str(error)
 else:raise AssertionError('re-decoded timestamp shift accepted')
assert (root/'bundle/notes/manifest.json').read_bytes()==prior_notes
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

test('channels preserve exact source PTS and masks without retaining decoded RGB',()=>{
 const root=fixture();try{
  const path=join(root,'bundle'),saved=manifest(path),observed=[...frames(path)];
  assert.equal(saved.channels.notes.status,'available');assert.equal(saved.channels.popup.status,'not_measured');
  assert.equal(observed.length,66);
  assert.deepEqual(observed[0].note_candidates.map(c=>c.role),['tap','hold_start','hold_end']);
  assert.deepEqual(observed[0].note_candidates.map(c=>c.candidate),[0,1,2]);assert.equal(observed[65].frame,65);
  assert.equal(observed[65].source_pts_seconds,31+65*.017);
  assert.equal(observed[65].playback_seconds,1+65*.017);
  assert.equal(readdirSync(path).some(name=>name.endsWith('.rgb.gz')),false);
  const masks=[...spatialMasks(path)];assert.equal(masks.length,66);assert.equal(masks[65].frame,65);
 }finally{rmSync(root,{recursive:true,force:true});}
});
test('independent channel reads ignore unrelated damaged channels but reject corruption in their own evidence',()=>{
 const root=fixture();try{
  const path=join(root,'bundle'),saved=manifest(path);
  const notes=Object.keys(saved.notes_stage.chunks[0].files).find(n=>n.endsWith('.notes.jsonl.gz'));
  const bytes=readFileSync(join(path,'notes',notes));bytes[bytes.length-5]^=1;writeFileSync(join(path,'notes',notes),bytes);
  assert.throws(()=>[...frames(path,{channel:'input'})],/not measured/);
  assert.equal([...frames(path,{channel:'timeline'})].length,66);
  assert.throws(()=>[...frames(path,{channel:'notes'})],/Corrupt/);
  writeFileSync(join(path,'notes/manifest.json'),'broken note metadata');
  assert.equal([...frames(path,{channel:'timeline'})].length,66);
  assert.equal([...spatialMasks(path)].length,66);
  writeFileSync(join(root,'source.mkv'),'changed original identity');
  assert.throws(()=>manifest(path),/source changed/);
 }finally{rmSync(root,{recursive:true,force:true});}
});
