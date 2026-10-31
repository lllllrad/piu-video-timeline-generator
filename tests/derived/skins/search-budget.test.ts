import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';

const script=String.raw`
import copy,json,os,tempfile
from pathlib import Path
from unittest.mock import patch
import cv2,numpy as np
from tests.play.skins.scenes import bank_at,render
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.build import build
from piu_timeline.play.skins.detector import SkinDetector,FORMAT
from piu_timeline.play.skins.matching import RegionSearch
from piu_timeline.play.skins.sampling import reference_scale,phases
from piu_timeline.play.skins.coordinates import validate_origin
from piu_timeline.play.skins.reuse import reusable_groups
from piu_timeline.tools.replay import child_environment

# Independent exhaustive region oracle, with no pruning or score sharing.
def exhaustive(searcher,template,bounds):
 left,top,right,bottom=bounds;h,w=template['mask'].shape
 search=searcher.image[top:bottom,left:right];scores=None;errors={}
 for region in template['regions']:
  a,b,c,d=region['box'];mask=region['mask']
  area=search[b:search.shape[0]-h+d,a:search.shape[1]-w+c]
  value=(cv2.matchTemplate(area,template['rgb'][b:d,a:c],cv2.TM_SQDIFF,mask=mask)/(3*int(mask.sum()))
    if mask.any() else np.full((search.shape[0]-h+1,search.shape[1]-w+1),np.inf,dtype='float32'))
  errors[region['name']]=np.maximum(value,0)
  normalized=errors[region['name']]/region.get('maximum_error',.015)
  scores=normalized if scores is None else np.maximum(scores,normalized)
 proposal=scores
 if 'cap'in errors:
  required={'cap',*template.get('cap_features',[])}
  proposal=np.maximum.reduce([errors[r['name']]/r.get('maximum_error',.015) for r in template['regions'] if r['name']in required])
 return scores,proposal,errors

with tempfile.TemporaryDirectory() as temporary:
 root=Path(temporary);legacy=bank_at(root);document=json.loads((root/'bank.json').read_text())
 document['reference_frame']={'kind':'full_game_crop','width':180,'height':300}
 # Repeated photographs of one pattern must retain every alias as provenance.
 document['templates'] += [{**copy.deepcopy(t),'id':'other-pose-'+t['id']} for t in document['templates']]
 (root/'bank.json').write_text(json.dumps(document));bank=load_bank(root/'bank.json')
 layout={'receptor_y':.08,'note_y_max':.95,'judgment_roi':[0,0,0,0],'combo_roi':[0,0,0,0],
  'lanes':[{'x':(40+i*20.0002)/180,'color':('blue','red','yellow','red','blue')[i]} for i in range(5)]}
 effective=reference_scale(bank,layout,180,300)
 legacy_scale=reference_scale(legacy,layout,180,300)
 objects=[{'kind':'tap','lane':0,'y':90},{'kind':'hold','lane':2,'y':130,'end_y':170},
          {'kind':'tap','lane':0,'y':220},{'kind':'tap','lane':4,'y':240}]
 image=render(objects,0,180,300,47,None,0)
 cv2.imwrite(str(root/'full.png'),image[:,:,::-1])
 spec={'skin':'generated-grid-build','spacing_pixels':20,'analysis_width':360,
  'reference_frame':{'kind':'full_game_crop','width':180,'height':300},'templates':[
   {'id':'cap','lane_kind':0,'role':'tap','source_image':'full.png','crop':[30,80,50,100],
    'anchor_pixels':[10,10],'regions':[{'name':'cap','box':[0,0,20,20]}]}]}
 (root/'spec.json').write_text(json.dumps(spec));built=load_bank(build(root/'spec.json',root/'built'))
 blank=render([],0,180,300,91,None,0)
 detector=SkinDetector(bank,layout,180,300);original=cv2.matchTemplate
 comparisons=[];observations=[]
 for rgb in (image,blank,image):
  with patch.object(cv2,'matchTemplate',wraps=original) as calls:
   optimized=detector.detect(rgb);fast=calls.call_count
  with patch.object(RegionSearch,'evaluate',exhaustive),patch.object(cv2,'matchTemplate',wraps=original) as calls:
   full=detector.detect(rgb);slow=calls.call_count
  assert optimized==full
  comparisons.append([fast,slow]);observations.append(optimized)
 caps=[{'lane':o['lane'],'role':o['role'],'y':round(o['y']*300,6)} for o in observations[0] if o['role']!='hold_body']
 templates={t['id']:t for t in bank['templates']}
 for observation in observations[0]:
  for candidate in [observation,*observation.get('alternatives',[])]:
   validate_origin(candidate,templates[candidate['template']],180,300,effective)
 scaled=SkinDetector(bank,layout,270,450)
 scaled_image=cv2.resize(image,(270,450),interpolation=cv2.INTER_AREA)
 scaled_found=scaled.detect(scaled_image)
 with patch.object(RegionSearch,'evaluate',exhaustive):assert scaled_found==scaled.detect(scaled_image)
 replay=reusable_groups({'skin_detector':{'bank_path':str(root/'bank.json'),
  'contract':{'bank':bank['contract'],'detector':FORMAT}}},{**bank,'reference_frame':{'kind':'full_game_crop','width':360,'height':600}})
 invalid=False
 document['reference_frame']['width']=0;(root/'bank.json').write_text(json.dumps(document))
 try:load_bank(root/'bank.json')
 except ValueError:invalid=True
 with patch.dict(os.environ,{},clear=True),patch.object(os,'sched_getaffinity',return_value=set(range(16))):
  env=child_environment(8)
 with patch.dict(os.environ,{'PIU_SKIN_JOBS':'3','OPENBLAS_NUM_THREADS':'2'},clear=True):override=child_environment(8)
 print(json.dumps({'scale':effective,'legacy_variants':len(phases(legacy_scale))**2*2,
  'variants':len(detector.templates),'references':len(bank['templates']),'caps':caps,
  'blank_empty':not observations[1],'frame_repeated':observations[0]==observations[2],
  'aliases_preserved':all(o['alternatives'] for o in observations[0]),'comparisons':comparisons,
  'scaled_reference':reference_scale(bank,layout,270,450),
  'scaled_caps':[{ 'lane':o['lane'],'role':o['role'],'y':o['y']*450/1.5}for o in scaled_found if o['role']!='hold_body'],
  'changed_grid_reuse':sorted(replay),'invalid_grid':invalid,
  'built_grid':built['reference_frame'],'built_scale':reference_scale(built,layout,180,300),
  'budget':{k:env[k] for k in ('PIU_SKIN_JOBS','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')},
  'override':{k:override[k] for k in ('PIU_SKIN_JOBS','OPENBLAS_NUM_THREADS')}}))
`;
const measured=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));

test('a declared source frame prevents rounded lane spacing from multiplying reference images',()=>{
  assert.equal(measured.scale,1);
  assert.equal(measured.legacy_variants,32);
  assert.equal(measured.variants,measured.references);
  assert.equal(measured.invalid_grid,true);
  assert.deepEqual(measured.changed_grid_reuse,[]);
  assert.deepEqual(measured.built_grid,{kind:'full_game_crop',width:360,height:600});
  assert.equal(measured.built_scale,.5);
});

test('cap-first pruning and exact score reuse preserve exhaustive observations and all simultaneous or later notes',()=>{
  const expected=[{lane:0,role:'tap',y:90},{lane:0,role:'tap',y:220},
    {lane:2,role:'hold_start',y:130},{lane:2,role:'hold_end',y:170},{lane:4,role:'tap',y:240}];
  assert.deepEqual(measured.caps,expected);
  assert.equal(measured.aliases_preserved,true);
  assert.equal(measured.blank_empty,true);
  assert.equal(measured.frame_repeated,true);
  for(const [fast,slow] of measured.comparisons) assert.ok(fast<slow/2,`${fast} comparisons versus ${slow}`);
  assert.equal(measured.scaled_reference,1.5);
  for(const note of expected) assert.ok(measured.scaled_caps.some(o=>o.lane===note.lane&&o.role===note.role&&Math.abs(o.y-note.y)<1));
});

test('the replay coordinator shares sixteen CPUs across eight plays and respects explicit worker settings',()=>{
  assert.deepEqual(measured.budget,{PIU_SKIN_JOBS:'2',OPENBLAS_NUM_THREADS:'1',OMP_NUM_THREADS:'1'});
  assert.deepEqual(measured.override,{PIU_SKIN_JOBS:'3',OPENBLAS_NUM_THREADS:'2'});
});
