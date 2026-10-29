import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';

const script=String.raw`
import json,math,tempfile,io
from copy import deepcopy
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import cv2,numpy as np
from piu_timeline.play.skins.sampling import weights,models
from piu_timeline.play.skins.subfeatures import account
from piu_timeline.play.skins.coordinates import registered_comparison
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.replay import refresh,detector_metadata
from piu_timeline.play.skins.reuse import reusable_groups
from tests.play.skins.scenes import bank_at,render
rng=np.random.default_rng(71);rgb=rng.integers(0,255,(8,8,3),dtype='uint8')
mask=np.ones((8,8),dtype=bool);mask[3]=False
source={'id':'cap','rgb':rgb,'mask':mask,'anchor_pixels':[4,4],
 'regions':[{'name':'cap','box':[0,0,8,8],'maximum_error':.002}]}
model=next(m for m in models(source,1.5)if m['sampling_phase_pixels']==[.5,.5])
image=np.zeros((30,32,3),dtype='uint8');image[5:13,3:11]=rgb
whole=cv2.resize(image,(48,45),interpolation=cv2.INTER_AREA).astype('float32')/255
sample_patch=whole[7:7+model['mask'].shape[0],4:4+model['mask'].shape[1]]
error=float(np.max(np.abs(model['rgb']-sample_patch)[model['support']]))
templates={'cap':{'cap_support':np.ones((4,4),dtype=bool)},'body':{'support':np.ones((2,2),dtype=bool)}}
templates['cap']['cap_support'][1,1]=False
cap={'template':'cap','role':'tap','lane':0,'bounds_pixels':[2,2,6,6]}
body={'template':'body','role':'hold_body','lane':0,'bounds_pixels':[4,4,6,6]}
results={}
for mode in ('contained','unsupported_hole','outside','other_lane','alternative_outside','stale_owner'):
 b=deepcopy(body)
 if mode=='unsupported_hole':b['bounds_pixels']=[2,2,4,4]
 if mode=='outside':b['bounds_pixels']=[5,5,7,7]
 if mode=='other_lane':b['lane']=1
 if mode=='alternative_outside':b['alternatives']=[{**deepcopy(b),'bounds_pixels':[5,5,7,7]}]
 if mode=='stale_owner':b['cap_subfeature']={'stale':True}
 images=[deepcopy(cap),b]if mode!='stale_owner'else[b]
 out=account(images,templates,10,10)[-1]
 assert out['role']=='hold_body' and out['bounds_pixels']==b['bounds_pixels']
 results[mode]=bool(out.get('cap_subfeature'))
template={'mask':np.ones((8,8)), 'regions':[{'name':'cap','maximum_error':.002}],'lane_kind':0}
bank={'anchor_registrations':{'cap':{'coordinate_uncertainty_pixels':1.}}}
sample={'template':'cap','y':.5,'region_errors':{'cap':0.},'reference_scale_y':1.5,'sampling_phase_pixels':[.5,.5]}
registration,_=registered_comparison(sample,bank,{'cap':template},0,50,100,1.5)
invalid=False
try:registered_comparison({**sample,'sampling_phase_pixels':[.25,.5]},bank,{'cap':template},0,50,100,1.5)
except ValueError:invalid=True
replays={}
for changed in ('body','caps'):
 with tempfile.TemporaryDirectory()as tmp:
  root=Path(tmp);old=root/'old';new=root/'new';old.mkdir();new.mkdir()
  old_bank=bank_at(old);bank_at(new)
  for path in new.glob('*.png'):
   is_body=path.stem.endswith('hold_body')
   if (changed=='body')!=is_body:continue
   pixels=cv2.imread(str(path),cv2.IMREAD_UNCHANGED)
   if is_body:pixels[0,0,0]=min(255,int(pixels[0,0,0])+1)
   else:pixels[:,:,:3]=np.minimum(pixels[:,:,:3].astype('int16')+50,255).astype('uint8')
   cv2.imwrite(str(path),pixels)
  new_bank=load_bank(new/'bank.json')
  layout={'receptor_y':.08,'note_y_max':.95,'combo_roi':[0,0,0,0],'judgment_roi':[0,0,0,0],
   'lanes':[{'x':(40+i*20)/180,'color':('blue','red','yellow','red','blue')[i]}for i in range(5)]}
  rgb=render([{'kind':'tap','lane':0,'y':80}],1/60,180,300,42,None,1)
  rgb=cv2.resize(rgb,(90,150),interpolation=cv2.INTER_AREA)
  observed=SkinDetector(old_bank,layout,90,150).detect(rgb)
  assert any(o.get('cap_subfeature')for o in observed)
  native={'source_pts_seconds':42.125+1/60,'playback_seconds':1/60,'skin_observations':observed,
   'notes':[o for o in observed if o['role']!='hold_body'],'combo':42}
  (root/'frames.jsonl').write_text(json.dumps(native)+'\n')
  media=root/'source.mkv';media.write_bytes(b'original recording')
  data={'media':{'path':str(media),'size_bytes':media.stat().st_size,'mtime_ns':media.stat().st_mtime_ns},
   'skin_detector':detector_metadata(old/'bank.json'),'layout':layout,'analysis_width':90,'analysis_height':150,
   'game_roi':[0,0,180,300],'start_seconds':1/60,'end_seconds':.05,'frame_count':1}
  assert reusable_groups(data,new_bank)=={f"{'caps'if changed=='body'else'body'}/{kind}"for kind in range(5)}
  from piu_timeline.play.skins import replay
  classify=replay.classified_frames
  def serial(frames,bank,*args):return classify(frames,bank,*args,jobs=1)
  with patch.object(replay,'decode_frames',return_value=iter([(native['source_pts_seconds'],1/60,rgb)])),patch.object(replay,'classified_frames',side_effect=serial),redirect_stdout(io.StringIO()):
   refresh(data,root,new/'bank.json')
  actual=json.loads((root/'frames.jsonl').read_text())
  assert actual['skin_observations']==SkinDetector(new_bank,layout,90,150).detect(rgb)
  assert actual['combo']==42 and media.read_bytes()==b'original recording'
  replays[changed]=any(o.get('cap_subfeature')for o in actual['skin_observations'])
print(json.dumps({'weights':weights(2,1.5,.5).tolist(),'maximum_rgb_error':error,
 'anchor':[4+model['anchor'][0],7+model['anchor'][1]],'unsupported_rows':bool(model['support'][5:7].any()),
 'subfeatures':results,'registration_scale':registration['native_cap_reference_scale_y'],'invalid_phase_rejected':invalid,'replay_ownership':replays}))
`;
const measured=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
test('source cell areas preserve fractional origin and whole-frame RGB sampling',()=>{
 assert.deepEqual(measured.weights,[[.5,0],[1,0],[0,1],[0,.5]]);
 assert.ok(measured.maximum_rgb_error<=.5/255+1e-6);
 assert.deepEqual(measured.anchor,[10.5,13.5]);
});
test('resampling cannot turn unsupported source rows into compared image coverage',()=>{
 assert.equal(measured.unsupported_rows,false);
});
test('cap subfeatures require every compared pixel and alternative in the same lane',()=>{
 assert.deepEqual(measured.subfeatures,{contained:true,unsupported_hole:false,outside:false,other_lane:false,alternative_outside:false,stale_owner:false});
});
test('native registration uses the actual sampling scale and rejects a foreign phase',()=>{
 assert.equal(measured.registration_scale,1.5);assert.equal(measured.invalid_phase_rejected,true);
});
test('partial-group replay reconstructs cap ownership and removes stale ownership after cap changes',()=>{
 assert.deepEqual(measured.replay_ownership,{body:true,caps:false});
});
