import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';

const script=String.raw`
import json,tempfile
from copy import deepcopy
from pathlib import Path
import numpy as np
from tests.play.skins.test_detector import examples
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.frame_centers import FrameCenters
from piu_timeline.play.observations.cache import tracking_notes
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);items,_=examples(root);bank=load_bank(root/'bank.json')
 layout={'receptor_y':.05,'note_y_max':.95,'lanes':[{'x':.1+i*.1}for i in range(5)]}
 detector=SkinDetector(bank,layout,200,300);image=np.zeros((300,200,3),dtype='uint8')
 image[80:120,10:30]=items[0][1]
 observed=detector.detect(image);caps=[(i,o)for i,o in enumerate(observed)if o['role']!='hold_body']
 assert len(caps)==1
 index,cap=caps[0]
 compact={**{k:v for k,v in cap.items()if k!='alternatives'},'skin_observation':index}
 frame={'playback_seconds':1.25,'source_pts_seconds':42.125,'notes':[compact],'skin_observations':observed}
 before=deepcopy(frame);centers=FrameCenters(detector)
 complete=centers.position(cap);reused=centers.position(tracking_notes(frame)[0]);limited=centers.position(compact)
 rejected=[]
 for mode in ['foreign-lane','changed-position','changed-template','invalid-index','body-index']:
  corrupt=deepcopy(frame);note=corrupt['notes'][0]
  if mode=='foreign-lane':note['lane']=1
  elif mode=='changed-position':note['y']+=.01
  elif mode=='changed-template':note['template']='foreign'
  elif mode=='invalid-index':note['skin_observation']=len(observed)
  else:corrupt['skin_observations'][index]['role']='hold_body'
  try:tracking_notes(corrupt)
  except ValueError:rejected.append(mode)
 result={'complete':complete,'reused':reused,'compact':limited,'unchanged':frame==before,'rejected':rejected,
  'full_rows':tracking_notes({'notes':[cap],'skin_observations':observed})==[cap]}
 print(json.dumps(result))
`;

test('compact native rows retain every pixel-qualified coordinate view during tracking replay',()=>{
 const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.ok(r.complete.anchors.length>1,'independently matched reference origins must reach the tracker');
 assert.equal(r.compact.anchors.length,1,'the compact row alone omits the additional observed views');
 assert.deepEqual(r.reused,r.complete);assert.equal(r.unchanged,true);assert.equal(r.full_rows,true);
 assert.deepEqual(r.rejected,['foreign-lane','changed-position','changed-template','invalid-index','body-index']);
});
