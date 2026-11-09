import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import type {RecordData} from '../../../src/piu_timeline/derived/types.ts';


const script=String.raw`
import copy,json,tempfile
from pathlib import Path
import cv2,numpy as np
from tests.play.skins.test_detector import examples
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.observations import observe
from piu_timeline.play.skins.coverage import ReferenceRows,image_spans
from piu_timeline.play.skins.sampling import key
results=[];invalid=[]
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);items,document=examples(root)
 pixels=cv2.imread(str(root/'hold_end.png'),cv2.IMREAD_UNCHANGED);pixels[15:35,:,:3]=255-pixels[15:35,:,:3]
 cv2.imwrite(str(root/'hold_end.png'),pixels)
 end=document['templates'][2];end.update(cap_role_identification='distinct_cap_features',cap_features=['terminal'])
 end['regions'].append({'name':'terminal','box':[2,30,18,35],'maximum_error':.001})
 layout={'receptor_y':.05,'note_y_max':.95,'combo_roi':[0,0,0,0],'judgment_roi':[0,0,0,0],
  'lanes':[{'x':.1+i*.1}for i in range(5)]}
 for scale in [.5,1,1.5,2]:
  for mode in ['known_anchor','known_anchor_offset','known_anchor_hidden','known_anchor_damaged','exposed_terminal','partial_body','hidden_terminal','damaged_terminal','unexplained_obstruction','stem','full_cap_declaration']:
   spec=copy.deepcopy(document)
   if mode.startswith('known_anchor'):
    locator=copy.deepcopy(spec['templates'][2]);locator.update(id='terminal-locator',role='tap',regions=[{'name':'cap','box':[2,30,18,35],'maximum_error':.001}]);locator.pop('cap_features');locator.pop('cap_role_identification');
    if mode in ('known_anchor_hidden','known_anchor_damaged'):locator['regions'][0]['box']=[2,15,18,20]
    if mode=='known_anchor_offset':locator.update(anchor_pixels=[10,23],native_center_pixels=[10,25])
    spec['templates'].append(locator)
   if mode=='full_cap_declaration':spec['templates'][2]['cap_role_identification']='distinct_full_cap'
   (root/'bank.json').write_text(json.dumps(spec));bank=load_bank(root/'bank.json')
   image=np.zeros((300,200,3),dtype='uint8');image[80:115,10:30]=pixels[:,:,:3][:,:,::-1]
   if mode in ['known_anchor','known_anchor_offset','known_anchor_damaged','exposed_terminal','full_cap_declaration','damaged_terminal']:
    image[80:100,10:30]=items[0][1][10:30]
   elif mode in ('hidden_terminal','known_anchor_hidden'):image[110:130,10:30]=items[0][1][10:30]
   elif mode=='partial_body':image[64:84,10:30]=items[0][1][10:30]
   elif mode=='unexplained_obstruction':image[95:100,10:30]=[180,15,140]
   else:image[50:180,16:24]=[25,140,210];image[95:115,10:30]=0
   if mode in ('damaged_terminal','known_anchor_damaged'):image[110:115,12:28]=[25,140,210]
   width,height=round(200*scale),round(300*scale);rgb=cv2.resize(image,(width,height),interpolation=cv2.INTER_AREA)
   detector=SkinDetector(bank,layout,width,height);found=detector.detect(rgb)
   tails=[o for o in found if o['role']=='hold_end'];case={'scale':scale,'mode':mode,'tails':tails}
   if tails:
    tail=tails[0];data={'analysis_width':width,'analysis_height':height,'layout':layout,
      'skin_detector':{'bank_path':str(root/'bank.json'),'contract':{'bank':bank['contract']}},
      'notes':[{'lane':0,'points':[[1.25,tail['y']*height]]}]}
    channel=observe(data,[{'playback_seconds':1.25,'source_pts_seconds':31.25,'skin_observations':found}])
    case.update(proof=channel['notes'][0],body_rows=image_spans(tail,ReferenceRows('body')),
                visible_pixels=sum(b-a for _,a,b in tail['visible_cap_runs']),
                full_pixels=int(detector.by_sampling[key(tail)]['cap_support'].sum()))
   results.append(case)
 for name,change in [('missing_features',{}),('tap_role',{'role':'tap'}),('body_role',{'role':'hold_body'})]:
  spec=copy.deepcopy(document)
  if name=='missing_features':spec['templates'][2].pop('cap_features')
  else:spec['templates'][2].update(change)
  (root/'bank.json').write_text(json.dumps(spec))
  try:load_bank(root/'bank.json')
  except ValueError:invalid.append(name)
 print(json.dumps({'results':results,'invalid':invalid}))
`;
const measured:RecordData=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{
 encoding:'utf8',maxBuffer:8*1024*1024,
}));

for(const result of measured.results)test(`terminal role requires an exposed discriminating feature: ${result.mode}, ${result.scale}`,()=>{
 if(result.mode==='partial_body'){
  assert.equal(result.tails.length,1);
  const tail=result.tails[0];
  assert.equal(tail.classification_status,'full_pattern');
  assert.equal(tail.connector_ownership.comparison_classification_status,'cap_only');
  assert.ok(tail.connector_ownership.full_region_error>.001);
  assert.ok(tail.connector_ownership.visible_connector_error<=.001);
  assert.ok(result.body_rows.length>0,'the actually visible body remains reusable');
  assert.ok(result.body_rows.every(([a,b])=>a>=84*result.scale&&b<=92*result.scale+1));
  assert.equal(result.proof.observations[0].source_pts_seconds,31.25);
  return;
 }
 if(!['exposed_terminal','known_anchor','known_anchor_offset'].includes(result.mode)){
  assert.deepEqual(result.tails,[],'hidden, damaged or unexplained pixels cannot establish the terminal role');
  return;
 }
 assert.equal(result.tails.length,1);
 const tail=result.tails[0];
 assert.equal(tail.classification_status,'cap_role_pattern');
 if(result.mode.startsWith('known_anchor')){
  const anchor=tail.occlusion_evidence.anchor_observation;
  const seed=tail.occlusion_evidence.position_seed;
  assert.equal((anchor??seed).template,'terminal-locator');
  if(anchor){
   assert.ok(Math.abs(anchor.registered_center_analysis_pixels[0]-20*result.scale)<=.5);
   assert.ok(Math.abs(anchor.registered_center_analysis_pixels[1]-105*result.scale)<=.5);
  }
  assert.ok(Math.abs(tail.y*300*result.scale-105*result.scale)<1e-8,'visible terminal pixels establish the actual position');
 }
 assert.equal(tail.role_evidence.method,'declared_distinct_cap_features');
 assert.deepEqual(tail.role_evidence.discriminating_features,['terminal']);
 assert.ok(result.visible_pixels<result.full_pixels,'the cap really is partially observed');
 assert.deepEqual(result.body_rows,[],'a role feature does not invent connector pixels');
 assert.equal(result.proof.status,'hold');
 assert.equal(result.proof.observations[0].source_pts_seconds,31.25);
 assert.equal(result.proof.observations[0].role_evidence.connection_confirmed,false);
});
test('feature-only endpoint declarations reject missing features and incompatible roles',()=>{
 assert.deepEqual(measured.invalid,['missing_features','tap_role','body_role']);
});
