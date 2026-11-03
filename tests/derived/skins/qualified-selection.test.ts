import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';
import {choose}from '../../../src/piu_timeline/derived/skins/selection.ts';
const script=String.raw`
from pathlib import Path
import json,tempfile,sys
sys.path.insert(0,str(Path.cwd()))
import numpy as np
from tests.play.skins.test_detector import examples
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);items,manifest=examples(root)
 manifest['templates']=[{**entry,'id':entry['id']+'-'+str(lane),'lane_kind':lane,
  'regions':[{**r,'maximum_error':.02}for r in entry['regions']]}for lane in range(3)for entry in manifest['templates']]
 (root/'bank.json').write_text(json.dumps(manifest));bank=load_bank(root/'bank.json')
 detector=SkinDetector(bank,{'receptor_y':.05,'note_y_max':.95,'lanes':[{'x':.1+i*.1}for i in range(5)]},200,300)
 candidates=[]
 for amount in [30,40]:
  observations=[]
  for window in range(3):
   for frame in range(2):
    time=10+window*2+frame/60;rgb=np.zeros((300,200,3),dtype='uint8');top=100-window*10-frame*2
    patch=np.clip(items[0][1].astype('int16')+amount,0,255).astype('uint8')
    for lane in range(3):rgb[top:top+len(patch),10+20*lane:30+20*lane]=patch
    observations.extend({**o,'window':window,'source_pts_seconds':100+time,'playback_seconds':time}for o in detector.detect(rgb)if o['template_role']!='hold_body')
  candidates.append({'selection':{'skin':'generated','revision':str(amount)},'observations':observations})
 print(json.dumps(candidates))
`;
const samples=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
test('native RGB satisfying reference-region bounds is sufficient skin evidence despite its lower ranking score',()=>{
 const accepted=samples[0],before=structuredClone(accepted);
 assert.ok(accepted.observations.length>=12);
 assert.ok(accepted.observations.every(o=>o.quality>=0&&o.quality<.5&&o.region_errors.cap<.02));
 const result=choose([accepted]);assert.equal(result.status,'selected');
 assert.deepEqual(result.selection,accepted.selection);assert.deepEqual(accepted,before);
});
test('pixel differences outside the reference bound remain rejected before skin selection',()=>{
 assert.deepEqual(samples[1].observations,[]);assert.equal(choose([samples[1]]).status,'unresolved');
});
