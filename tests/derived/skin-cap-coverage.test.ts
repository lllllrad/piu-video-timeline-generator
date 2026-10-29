import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
const script=String.raw`
import copy,json,tempfile
from pathlib import Path
import cv2,numpy as np
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.coverage import reference_rows,image_spans
from piu_timeline.play.skins.temporal import coverage_losses,measured_steps
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);glyph=np.random.default_rng(37).integers(45,230,(20,20,3),dtype='uint8')
 reference=np.zeros((50,40,3),dtype='uint8');reference[10:30,10:30]=glyph;reference[32:40,16:24]=[25,140,210]
 cv2.imwrite(str(root/'start.png'),np.dstack([reference[:,:,::-1],np.full((50,40),255,dtype='uint8')]))
 entries=[]
 for name,box in [('upper',[10,10,30,28]),('lower',[10,12,30,30])]:
  entries.append({'id':name,'role':'hold_start','lane_kind':0,'image':'start.png','anchor_pixels':[20,20],
   'sampling_context':[[0,0,40,50]],'regions':[{'name':'cap','box':box,'maximum_error':.001},
   {'name':'connection','box':[16,32,24,40],'maximum_error':.001}]})
 path=root/'bank.json';path.write_text(json.dumps({'schema':1,'skin':'generated-complementary-caps','spacing_pixels':20,'templates':entries}))
 bank=load_bank(path);layout={'receptor_y':.05,'note_y_max':.95,'judgment_roi':[0,0,0,0],'combo_roi':[0,0,0,0],
  'lanes':[{'x':.1+i*.1}for i in range(5)]};detector=SkinDetector(bank,layout,200,300)
 data={'analysis_width':200,'analysis_height':300,'layout':layout,'notes':[{'lane':0,'points':[]}],
  'skin_detector':{'bank_path':str(path),'contract':{'bank':bank['contract']}}}
 frames=[];caps=[]
 for time,y in [(1.,110),(1.025,105)]:
  image=np.zeros((300,200,3),dtype='uint8');image[y-10:y+10,10:30]=glyph
  found=detector.detect(image);cap=next(o for o in found if o['lane']==0 and abs(o['y']*300-y)<1e-6)
  frames.append({'playback_seconds':time,'source_pts_seconds':40+time,'skin_observations':found});caps.append(cap)
  data['notes'][0]['points'].append([time,cap['y']*300])
 rows=reference_rows(data,cap_only=True)
 primary=[];combined=[]
 for cap in caps:
  only=copy.deepcopy(cap);only['alternatives']=[]
  primary.append(image_spans(only,rows,cap_only=True));combined.append(image_spans(cap,rows,cap_only=True))
 steps=measured_steps(data,frames)
 def losses(last):
  proof=[{'time':1.,'lane':0,'covered_bounds_pixels':[100,120]}]
  proof.extend({'time':1.025,'lane':0,'covered_bounds_pixels':span}for span in last)
  return coverage_losses(data,frames,proof,steps)
 rejected=copy.deepcopy(caps[1])
 for alt in rejected['alternatives']:alt['classification_status']='conflict'
 print(json.dumps({'caps':caps,'primary':primary,'combined':combined,'lost_primary':losses(primary[1]),
  'lost_combined':losses(combined[1]),'rejected':image_spans(rejected,rows,cap_only=True)}))
`;
const observed=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
test('independently matched cap alternatives retain their actual positive boundary rows',()=>{
  assert.ok(observed.caps.every(c=>c.role==='unknown'&&c.classification_status==='cap_only'));
  assert.ok(observed.caps.every(c=>c.region_errors.connection>.001));
  assert.deepEqual(observed.primary,[[[100,118]],[[95,113]]]);
  assert.ok(observed.combined[0].some(s=>s[0]===102&&s[1]===120));
  assert.ok(observed.combined[1].some(s=>s[0]===97&&s[1]===115));
  assert.ok(observed.combined.every((spans,i)=>spans.every(s=>s[0]>=100-5*i&&s[1]<=120-5*i)),
    'failed connection pixels cannot supply cap coverage');
});
test('the extra positively compared rows resolve the loss without growing a coverage tolerance',()=>{
  assert.equal(observed.lost_primary.length,1);
  const gap=observed.lost_primary[0].missing_intervals_pixels;
  assert.equal(gap.length,1);
  assert.ok(Math.abs(gap[0][0]-113)<1e-9&&Math.abs(gap[0][1]-115)<1e-9);
  assert.deepEqual(observed.lost_combined,[]);
});
test('conflicted alternative comparisons cannot fill missing rows',()=>{
  assert.deepEqual(observed.rejected,observed.primary[1]);
});
