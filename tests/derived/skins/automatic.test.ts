import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
const script=String.raw`
import json,tempfile,os
from pathlib import Path
from unittest.mock import patch
import cv2,numpy as np
from tests.play.skins.test_detector import examples
from piu_timeline.play.skins.repository import publish
from piu_timeline.play.skins.automatic import prepare,retained,cache_path
from piu_timeline.play.skins.replay import selected_bank
from piu_timeline.play.skins import automatic
from piu_timeline.play import analysis
with tempfile.TemporaryDirectory()as temporary:
 root=Path(temporary);repo=root/'repo';(repo/'.git').mkdir(parents=True)
 choices=[];tap=None
 for skin,invert in [('generated-a',False),('generated-b',True)]:
  assets=root/skin;assets.mkdir();items,manifest=examples(assets);manifest['skin']=skin
  if tap is None:tap=items[0][1]
  manifest['templates']=[{**t,'id':t['id']+'-'+str(lane),'lane_kind':lane}for lane in range(5)for t in manifest['templates']]
  (assets/'bank.json').write_text(json.dumps(manifest))
  if invert:
   for image in assets.glob('*.png'):
    rgb=cv2.imread(str(image),cv2.IMREAD_UNCHANGED);rgb[:,:,:3]=255-rgb[:,:,:3];cv2.imwrite(str(image),rgb)
  publish(assets/'bank.json','one',repo)
  choices.append({'skin':skin,'revision':'one'})
 registry=repo/'skins/automatic.json';registry.write_text(json.dumps({'schema':1,'candidates':choices}))
 source=root/'data/example';(source/'analysis').mkdir(parents=True)
 video=root/'source.mkv';video.write_bytes(b'original recording');stat=video.stat()
 document={'media':{'path':str(video),'size_bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns},'game_roi':[0,0,200,300],
  'segments':[{'start_seconds':1.,'end_seconds':11.,'chart':'S10','players':{}}]}
 metadata=source/'analysis/analysis.json';metadata.write_text(json.dumps(document))
 layout={'receptor_y':.05,'combo_roi':[.4,.5,.2,.1],'lanes':[{'x':.1+i*.1,'color':'blue'}for i in range(5)]}
 options={'width':200,'layout':layout};calls=[]
 def decode(record,start,end,roi,width):
  window=len(calls);calls.append(start)
  for i in range(8):
   rgb=np.zeros((300,200,3),dtype='uint8');top=100-window*6-i
   for lane in range(3):rgb[top:top+40,10+lane*20:30+lane*20]=tap
   yield 30+start+i/60,start+i/60,rgb
 with patch('piu_timeline.charts.data.default_repository',return_value=repo):
  with patch('piu_timeline.play.skins.automatic.decode_frames',side_effect=decode):chosen=prepare(source,1,document,options)
  evidence=json.loads(cache_path(source,1).read_text());first_calls=len(calls)
  with patch('piu_timeline.play.skins.automatic.decode_frames',side_effect=AssertionError('cached selection must not decode')):
   reused=prepare(source,1,document,options)==chosen and retained(source,1,options)==chosen
  before_signature=automatic.signature(source,1);native_call=automatic.call
  def altered_policy(operation,*args):
   value=native_call(operation,*args)
   return {**value,'minimum_quality':.99}if operation=='skinSelection.policy'else value
  with patch.object(automatic,'call',side_effect=altered_policy):
   policy_invalid=retained(source,1,options)is None and automatic.signature(source,1)!=before_signature
  original=cache_path(source,1).read_text();tampered=json.loads(original);tampered['decision']['status']='unresolved'
  cache_path(source,1).write_text(json.dumps(tampered))
  try:retained(source,1,options);tamper_rejected=False
  except ValueError:tamper_rejected=True
  cache_path(source,1).write_text(original)
  video.write_bytes(b'changed recording')
  try:retained(source,1,options);media_invalid=False
  except ValueError:media_invalid=True
  video.write_bytes(b'original recording');os.utime(video,ns=(stat.st_atime_ns,stat.st_mtime_ns))
  changed={**document,'segments':[{**document['segments'][0],'start_seconds':1.1}]};metadata.write_text(json.dumps(changed))
  window_invalid=retained(source,1,options)is None;metadata.write_text(json.dumps(document))
  width_invalid=retained(source,1,{**options,'width':400})is None
  manual=selected_bank(source,1,str(repo/'skins/banks/generated-b/one/bank.json'))
  invoked=[]
  def stop(*args,**kwargs):invoked.append(kwargs['note_skin']);raise RuntimeError('native boundary')
  with patch.object(analysis,'LOCAL_DATA',root/'data'),patch.object(analysis,'source_id',return_value='example'),patch.object(analysis,'analyze_play',side_effect=stop),patch('piu_timeline.play.skins.automatic.prepare',return_value=chosen)as automatic:
   try:analysis.run('example',**options)
   except RuntimeError:pass
   workflow_automatic=automatic.call_count==1 and invoked==[chosen]
  invoked.clear()
  with patch.object(analysis,'LOCAL_DATA',root/'data'),patch.object(analysis,'source_id',return_value='example'),patch.object(analysis,'analyze_play',side_effect=stop),patch('piu_timeline.play.skins.automatic.prepare',side_effect=AssertionError('explicit selection takes precedence')):
   try:analysis.run('example',note_skin=manual,**options)
   except RuntimeError:pass
  explicit_first=invoked==[manual]
  # A duplicate appearance under another registered revision is ambiguous.
  publish(root/'generated-a/bank.json','two',repo)
  registry.write_text(json.dumps({'schema':1,'candidates':choices+[{'skin':'generated-a','revision':'two'}]}))
  registry_invalid=retained(source,1,options)is None
  calls.clear()
  with patch('piu_timeline.play.skins.automatic.decode_frames',side_effect=decode):
   try:prepare(source,1,document,options);ambiguous=False
   except ValueError as error:ambiguous='ambiguous_skin_images'in str(error)
  with patch('piu_timeline.play.skins.automatic.decode_frames',side_effect=AssertionError('unchanged failed evidence must not decode again')):
   try:prepare(source,1,document,options);failed_reused=False
   except ValueError:failed_reused=True
  print(json.dumps({'chosen':Path(chosen).parent.parent.name,'decision':evidence['decision'],'samples':len(evidence['samples']),
   'policy_invalid':policy_invalid,'tamper_rejected':tamper_rejected,'media_invalid':media_invalid,
   'calls':first_calls,'reused':reused,'window_invalid':window_invalid,'width_invalid':width_invalid,
   'workflow_automatic':workflow_automatic,'explicit_first':explicit_first,'registry_invalid':registry_invalid,
   'ambiguous':ambiguous,'failed_reused':failed_reused,'media_preserved':video.read_bytes()==b'original recording'}))
`;
const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}).trim().split('\n').at(-1));
test('registered native images select one bank and retain independent source-bound proof',()=>{
 assert.equal(r.chosen,'generated-a');assert.equal(r.decision.status,'selected');assert.equal(r.calls,6);
 assert.ok(r.samples>=4);assert.equal(r.media_preserved,true);
});
test('selection cache reuses evidence and invalidates changed windows, geometry or candidate registry',()=>{
 for(const key of['reused','window_invalid','width_invalid','registry_invalid','policy_invalid','media_invalid','tamper_rejected'])assert.equal(r[key],true,key);
});
test('the public play command uses automatic selection while explicit selection takes precedence',()=>{
 assert.equal(r.workflow_automatic,true);assert.equal(r.explicit_first,true);
});
test('ambiguous banks fail explicitly and unchanged failed evidence does not decode repeatedly',()=>{
 assert.equal(r.ambiguous,true);assert.equal(r.failed_reused,true);
});
