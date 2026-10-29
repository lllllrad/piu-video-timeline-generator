import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
const script=String.raw`
import copy,json,tempfile
from pathlib import Path
import cv2,numpy as np
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector,FORMAT
from piu_timeline.play.skins.anchors import cap_reference
from piu_timeline.play.skins.reuse import reusable_groups
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);reference=np.zeros((100,40,3),dtype='uint8')
 reference[:70,12:28]=[225,200,40];reference[:70,12:14]=255;reference[:70,26:28]=255;reference[68:70,12:28]=255
 cv2.imwrite(str(root/'tail.png'),np.dstack([reference[:,:,::-1],np.full((100,40),255,dtype='uint8')]))
 entry={'id':'tail','role':'hold_end','lane_kind':0,'image':'tail.png','anchor_pixels':[20,56],
  'sampling_context':[[0,0,40,100]],'regions':[{'name':'cap','box':[12,10,28,70]}, {'name':'connection','box':[12,0,28,10]}]}
 def bank(name,feature=False,required=False):
  item=copy.deepcopy(entry)
  if feature:item['regions'].append({'name':'terminal','box':[16,66,24,70]})
  if required:item['cap_features']=['terminal']
  path=root/(name+'.json');path.write_text(json.dumps({'schema':1,'skin':'generated-terminal','spacing_pixels':20,'templates':[item]}))
  return load_bank(path),path
 plain,plainpath=bank('plain');partial,partialpath=bank('partial',True);required,path=bank('required',True,True)
 results=[]
 for scale in [.5,1,1.5]:
  width,height=round(200*scale),round(300*scale)
  layout={'receptor_y':.05,'note_y_max':.95,'judgment_roi':[0,0,0,0],'combo_roi':[0,0,0,0],
   'lanes':[{'x':.1+i*.1}for i in range(5)]}
  scenes={}
  for mode in ['stem','end']:
   image=np.zeros((300,200,3),dtype='uint8');bottom=280 if mode=='stem'else 194
   image[40:bottom,12:28]=[225,200,40];image[40:bottom,12:14]=255;image[40:bottom,26:28]=255
   if mode=='end':image[192:194,12:28]=255
   scenes[mode]=cv2.resize(image,(width,height),interpolation=cv2.INTER_AREA)
  result={'scale':scale}
  for name,b in [('plain',plain),('partial',partial),('required',required)]:
   detector=SkinDetector(b,layout,width,height)
   for mode,image in scenes.items():
    found=[o for o in detector.detect(image)if o['role']!='hold_body']
    result[name+'_'+mode]=[{'role':o['role'],'y':o['y']*height,'region_errors':o['region_errors']}for o in found]
  results.append(result)
 saved={'skin_detector':{'bank_path':str(partialpath),'contract':{'bank':partial['contract'],'detector':FORMAT}}}
 invalid=[];base=json.loads(path.read_text())
 for name,change in [('absent',['absent']),('duplicate',['terminal','terminal']),('reserved',['connection']),('invalid_type','terminal')]:
  doc=copy.deepcopy(base);doc['templates'][0]['cap_features']=change;bad=root/'bad.json';bad.write_text(json.dumps(doc))
  try:load_bank(bad)
  except ValueError:invalid.append(name)
 doc=copy.deepcopy(base);doc['templates'][0]['regions'][-1]['box']=[16,68,24,72];bad.write_text(json.dumps(doc))
 try:load_bank(bad)
 except ValueError:invalid.append('outside_cap')
 print(json.dumps({'results':results,'invalid':invalid,'reused':sorted(reusable_groups(saved,required)),
  'bound_feature':cap_reference(partial,partial['templates'][0])!=cap_reference(required,required['templates'][0]),
  'contract':required['contract'].get('cap_features'),'legacy_contract':plain['contract'].get('cap_features')}))
`;
const observed=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
for(const r of observed.results)test(`terminal shape is independently required at source scale ${r.scale}`,()=>{
  assert.ok(r.plain_stem.some(c=>c.role==='hold_end'),'body-dominated average can match a stem');
  assert.ok(r.partial_stem.some(c=>c.role==='unknown'),'an optional terminal check leaves false cap candidates');
  assert.deepEqual(r.required_stem,[],'absent terminal shape cannot create any cap identity');
  assert.equal(r.required_end.length,1);
  assert.equal(r.required_end[0].role,'hold_end');
  assert.ok(Math.abs(r.required_end[0].y-180*r.scale)<1e-6);
});
test('cap-feature declarations bind acquisition reuse and anchor proof identity',()=>{
  assert.ok(!observed.reused.includes('caps'));
  assert.equal(observed.bound_feature,true);
  assert.equal(observed.legacy_contract,null);
  assert.deepEqual(observed.contract,{schema:1,method:'independently_required_cap_regions'});
});
test('missing, duplicate, reserved and out-of-cap feature declarations fail explicitly',()=>{
  assert.deepEqual(observed.invalid,['absent','duplicate','reserved','invalid_type','outside_cap']);
});
