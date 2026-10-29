import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
const script=String.raw`
import copy,json,tempfile
from pathlib import Path
import numpy as np
from tests.play.skins.test_detector import examples
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);items,doc=examples(root);entry=doc['templates'][0];entry['lane_kind']=1
 entry['source_evidence']={'lane':1,'lane_centers_x':[.1,.2,.3,.4,.5],
  'source_crop':[30,80,50,120],'reference_dimensions':[200,300]};doc['templates']=[entry]
 path=root/'review.json';path.write_text(json.dumps(doc));bank=load_bank(path)
 image=np.zeros((300,200,3),dtype='uint8');image[80:120,30:50]=items[0][1]
 layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1}for i in range(5)]}
 caps=[o for o in SkinDetector(bank,layout,200,300).detect(image)if o['role']!='hold_body']
 rejected=[]
 for mode in ['wrong_direction','wrong_source_lane','invalid_lane','wrong_crop','ambiguous_lane']:
  changed=copy.deepcopy(doc);t=changed['templates'][0];e=t['source_evidence']
  if mode=='wrong_direction':t['lane_kind']=3
  if mode=='wrong_source_lane':t['lane_kind']=3;e['lane']=3
  if mode=='invalid_lane':e['lane']=True
  if mode=='wrong_crop':e['source_crop'][2]+=1
  if mode=='ambiguous_lane':e['source_crop']=[40,80,60,120]
  path.write_text(json.dumps(changed))
  try:load_bank(path)
  except ValueError:rejected.append(mode)
 print(json.dumps({'caps':[{'lane':o['lane'],'role':o['role'],'y':o['y']*300}for o in caps],'rejected':rejected}))
`;
const observed=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
test('a source-bound reference locates its actual source column',()=>{
 assert.deepEqual(observed.caps,[{lane:1,role:'tap',y:100}]);
});
test('an internally consistent wrong direction cannot override the source crop geometry',()=>{
 assert.deepEqual(observed.rejected,['wrong_direction','wrong_source_lane','invalid_lane','wrong_crop','ambiguous_lane']);
});
