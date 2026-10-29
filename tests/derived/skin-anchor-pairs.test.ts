import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {compare} from '../../src/piu_timeline/derived/skins/anchors.ts';
const script=String.raw`
import json,tempfile
from pathlib import Path
import cv2,numpy as np
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.__main__ import compare_anchors
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);ref=np.zeros((64,64,3),dtype='uint8');glyph=np.random.default_rng(16).integers(40,210,(20,20,3),dtype='uint8');ref[22:42,22:42]=glyph
 cv2.imwrite(str(root/'cap.png'),np.dstack([ref[:,:,::-1],np.full((64,64),255,dtype='uint8')]))
 templates=[{'id':name,'role':'tap','lane_kind':0,'image':'cap.png','anchor_pixels':[32,y],
  'sampling_context':[[0,0,64,64]],'regions':[{'name':'cap','box':[22,22,42,42],'maximum_error':.001}]}
  for name,y in [('first',32),('second',38)]]
 path=root/'bank.json';path.write_text(json.dumps({'schema':1,'skin':'generated-anchor-offset','spacing_pixels':40,'templates':templates}));bank=load_bank(path);results=[]
 for scale in [.5,1,1.5]:
  width,height=round(240*scale),round(300*scale);layout={'receptor_y':.05,'note_y_max':.95,'lanes':[{'x':(40+40*i)/240}for i in range(5)]};detector=SkinDetector(bank,layout,width,height);frames=[]
  for i in range(2):
   image=np.zeros((300,240,3),dtype='uint8');y=180-5*i;image[y-10:y+10,30:50]=glyph
   image=cv2.resize(image,(width,height),interpolation=cv2.INTER_AREA)
   frames.append({'playback_seconds':1+i*.025,'source_pts_seconds':71.25+i*.025,'observations':detector.detect(image)})
  results.append({'height':height,'scale':scale,'frames':frames})
 data={'bank':bank['contract'],'analysis_width':width,'analysis_height':height,'media':{'fixture':'generated_rgb'},'frames':frames};source=root/'observations.json';source.write_text(json.dumps(data))
 compare_anchors(source,path,root/'review.json');review=json.loads((root/'review.json').read_text())
 data['bank']={};source.write_text(json.dumps(data));stale=False
 try:compare_anchors(source,path,root/'stale.json')
 except ValueError:stale=True
 print(json.dumps({'results':results,'templates':templates,'review':review,'stale_rejected':stale}))
`;
const output=execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}).trim().split('\n');
const observed=JSON.parse(output.at(-1));
for(const scene of observed.results)test(`same RGB cap reveals the reference-only anchor offset at scale ${scene.scale}`,()=>{
 const original=structuredClone(scene.frames),result=compare(scene.frames,scene.height,observed.templates);
 assert.equal(result.pairs.length,1);const pair=result.pairs[0];
 assert.deepEqual(pair.templates,['first','second']);assert.equal(pair.observations,2);
 assert.ok(Math.abs(pair.median_delta_pixels-6*scene.scale)<1e-6);
 assert.ok(pair.delta_range_pixels.every(v=>Math.abs(v-6*scene.scale)<1e-6));
 assert.deepEqual(pair.samples.map(s=>s.source_pts_seconds),[71.25,71.275]);
 assert.deepEqual(scene.frames,original);
});
test('review binds the exact bank without decoding source media',()=>{
 assert.equal(observed.stale_rejected,true);
 assert.deepEqual(observed.review.media,{fixture:'generated_rgb'});
 assert.equal(observed.review.pairs.length,1);
});
test('missing required cap-feature evidence and invalid timelines cannot supply an anchor pair',()=>{
 const scene=observed.results[1],templates=structuredClone(observed.templates);
 templates[1].cap_features=['terminal'];templates[1].regions.push({name:'terminal',maximum_error:.001});
 assert.deepEqual(compare(scene.frames,scene.height,templates).pairs,[]);
 assert.throws(()=>compare([],scene.height,observed.templates),/requires native/);
 assert.throws(()=>compare([...scene.frames].reverse(),scene.height,observed.templates),/timeline/);
});
