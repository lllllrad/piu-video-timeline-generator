import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';

const script=String.raw`
import json,tempfile
from pathlib import Path
import cv2,numpy as np
from tests.play.skins.scenes import appearance_bank,render,bank_at,cap as glyph
from tests.play.skins.reference_centers import certify
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.frame_centers import FrameCenters

with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);appearance_bank(root,3,4,False,'generated')
 bank=certify(root/'bank.json');results=[]
 objects=[{'kind':'tap','lane':0,'y':130},{'kind':'hold','lane':3,'y':150,'end_y':220},
          {'kind':'tap','lane':4,'y':260}]
 for scale in [.5,1,1.5,2]:
  width,height=round(180*scale),round(300*scale)
  layout={'receptor_y':.08,'note_y_max':.95,'judgment_roi':[0,0,0,0],'combo_roi':[0,0,0,0],
   'lanes':[{'x':(40+i*20)/180}for i in range(5)]}
  detector=SkinDetector(bank,layout,width,height);centers=FrameCenters(detector)
  for frame in range(6):
   time=frame*.025
   image=render(objects,time,180,300,71,None,frame,appearance=frame%3)
   image=cv2.resize(image,(width,height),interpolation=cv2.INTER_AREA)
   caps=[o for o in detector.detect(image)if o['role']!='hold_body']
   measured=centers.positions(caps)
   expected=[(o['lane'],round(y-80*time)*scale)for o in objects
             for y in([o['y'],o['end_y']]if o['kind']=='hold'else[o['y']])]
   results.append({'scale':scale,'appearance':frame%3,'expected':expected,
    'observed':[{'lane':cap['lane'],'center':position['center'],
      'failure':position['measurement'].get('native_cap_registration_status')}
      for cap,position in zip(caps,measured)]})
 flat=root/'flat';flat.mkdir()
 glyphs=[np.tile(glyph(k)[8:9],(20,1,1))for k in range(5)]
 bank_at(flat,glyphs=glyphs);flat_bank=certify(flat/'bank.json')
 layout={'receptor_y':.08,'note_y_max':.95,'judgment_roi':[0,0,0,0],'combo_roi':[0,0,0,0],
  'lanes':[{'x':(40+i*20)/180}for i in range(5)]}
 rgb=np.zeros((300,180,3),dtype='uint8');rgb[70:230,30:50]=np.tile(glyphs[0][0:1],(160,1,1))
 detector=SkinDetector(flat_bank,layout,180,300)
 candidates=[o for o in detector.detect(rgb)if o['role']!='hold_body']
 measured=FrameCenters(detector).positions(candidates)
 print(json.dumps({'scenes':results,'flat':[
  {'center':p['center'],'failure':p['measurement'].get('native_cap_registration_status')}for p in measured]}))
`;

test('native pixels localize taps and both hold boundaries across animation poses, movement and image scales',()=>{
 const results=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.equal(results.scenes.length,24);
 assert.equal(results.scenes.reduce((n,r)=>n+r.observed.length,0),96);
 for(const scene of results.scenes){
  assert.equal(scene.observed.length,scene.expected.length,JSON.stringify(scene));
  for(const observed of scene.observed){
   assert.ok(observed.center,JSON.stringify(scene));
   assert.equal(observed.center.uncertaintyPixels,0);
   assert.equal(observed.failure,null);
  }
  for(const [lane,y]of scene.expected){
   const epsilon=64*Number.EPSILON*Math.max(1,Math.abs(y));
   assert.equal(scene.observed.filter(o=>o.lane===lane&&Math.abs(o.center.yPixels-y)<=epsilon).length,1,JSON.stringify(scene));
  }
 }
 assert.ok(results.flat.length>0);
 for(const observed of results.flat){
  assert.equal(observed.center,null);
  assert.equal(observed.failure,'image_localization_pixels_unqualified');
 }
});
