import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';

const script=String.raw`
import json,tempfile
from pathlib import Path
from unittest.mock import patch
import cv2
from tests.play.skins import scenes
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.replay import refresh,detector_metadata
from piu_timeline.play.skins.reuse import reusable_groups

results=[]
with tempfile.TemporaryDirectory()as tmp:
 for scale in [.5,1.5]:
  root=Path(tmp)/str(scale);root.mkdir();old=root/'old';new=root/'new';old.mkdir();new.mkdir()
  previous_bank=scenes.bank_at(old);scenes.bank_at(new)
  pose=new/'pose';pose.mkdir();scenes.bank_at(pose,glyphs=[scenes.cap(i,1)for i in range(5)])
  document=json.loads((new/'bank.json').read_text())
  for entry in json.loads((pose/'bank.json').read_text())['templates']:
   if entry['lane_kind']==4 and entry['role']!='hold_body':
    document['templates'].append({**entry,'id':'extra-'+entry['id'],'image':'pose/'+entry['image']})
  (new/'bank.json').write_text(json.dumps(document));bank=load_bank(new/'bank.json')
  width,height=round(280*scale),round(300*scale)
  layout={'receptor_y':.05,'note_y_max':.95,'judgment_roi':[0,0,0,0],'combo_roi':[0,0,0,0],
   'lanes':[{'x':(40+i*20)/280,'color':('blue','red','yellow','red','blue')[i%5]}for i in range(10)]}
  objects=[{'kind':'tap','lane':i,'y':120}for i in range(10)if i%5!=4]
  objects += [{'kind':'hold','lane':4,'y':100,'end_y':180},{'kind':'tap','lane':9,'y':140}]
  original_cap=scenes.cap
  def glyph(kind,appearance=0):return original_cap(kind,1 if kind==4 else 0)
  images=[]
  with patch.object(scenes,'cap',side_effect=glyph):
   for i in range(3):
    rgb=scenes.render(objects,i/60,280,300,71+i,None,i)
    images.append(cv2.resize(rgb,(width,height),interpolation=cv2.INTER_AREA))
  before=SkinDetector(previous_bank,layout,width,height);complete=SkinDetector(bank,layout,width,height)
  frames=[];expected=[];decoded=[]
  for i,rgb in enumerate(images):
   pts,time=31.367+i/60,1+i/60;observations=before.detect(rgb)
   frames.append({'source_pts_seconds':pts,'playback_seconds':time,'combo':4+i,
    'skin_observations':observations,'notes':[o for o in observations if o['role']!='hold_body']})
   expected.append(json.loads(json.dumps(complete.detect(rgb))));decoded.append((pts,time,rgb))
  trace=''.join(json.dumps(f)+'\n'for f in frames);(root/'frames.jsonl').write_text(trace)
  source=root/'source.mkv';source.write_bytes(b'original source media')
  data={'media':{'path':str(source),'size_bytes':source.stat().st_size,'mtime_ns':source.stat().st_mtime_ns},
   'skin_detector':detector_metadata(old/'bank.json'),'layout':layout,'analysis_width':width,'analysis_height':height,
   'game_roi':[0,0,width,height],'start_seconds':1.,'end_seconds':1.05,'frame_count':3}
  reused=sorted(reusable_groups(data,bank));selected=[]
  from piu_timeline.play.skins import replay
  classify=replay.classified_frames
  def changed_only(decoded,subset,*args):
   selected.extend((t['lane_kind'],t['role'])for t in subset['templates'])
   return classify(decoded,subset,*args,jobs=1)
  with patch.object(replay,'decode_frames',return_value=iter(decoded)),patch.object(replay,'classified_frames',side_effect=changed_only):
   refresh(data,root,new/'bank.json')
  actual=[json.loads(line)for line in (root/'frames.jsonl').read_text().splitlines()]
  results.append({'scale':scale,'reused':reused,'selected':selected,
   'exact_full_equivalence':[f['skin_observations']for f in actual]==expected,
   'before_caps':[len(f['notes'])for f in frames],'after_caps':[len(f['notes'])for f in actual],
   'preserved':[ {k:f[k]for k in ('source_pts_seconds','playback_seconds','combo')}for f in actual],
   'original':[ {k:f[k]for k in ('source_pts_seconds','playback_seconds','combo')}for f in frames],
   'changed_lanes':sorted({o['lane']for f in actual for o in f['notes']if o['lane']%5==4}),
   'source_preserved':source.read_bytes()==b'original source media'})
print(json.dumps(results))
`;
const results=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{
 encoding:'utf8',maxBuffer:8*1024*1024}).trim().split('\n').at(-1));
for(const r of results)test(`one new cap appearance reuses other lane kinds with full-detection equivalence: ${r.scale}`,()=>{
 assert.deepEqual(r.reused,['body/0','body/1','body/2','body/3','body/4','caps/0','caps/1','caps/2','caps/3']);
 assert.ok(r.selected.length>0);
 assert.ok(r.selected.every(([kind,role])=>kind===4&&role!=='hold_body'));
 assert.deepEqual(r.before_caps,[8,8,8]);assert.deepEqual(r.after_caps,[11,11,11]);
 assert.deepEqual(r.changed_lanes,[4,9]);
 assert.equal(r.exact_full_equivalence,true,'including alternatives, bodies and recomputed cap-subfeature ownership');
 assert.deepEqual(r.preserved,r.original);assert.equal(r.source_preserved,true);
});
