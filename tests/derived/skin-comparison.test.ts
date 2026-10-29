import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';

const script=String.raw`
import copy,json,tempfile
from pathlib import Path
import cv2,numpy as np
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.build import build
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.sampling import models
from piu_timeline.play.skins.anchors import cap_reference
from piu_timeline.play.skins.reuse import reusable_groups
from piu_timeline.play.skins.detector import FORMAT
from piu_timeline.play.skins.subfeatures import account
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);rgb=np.full((240,320,3),[12,14,18],dtype='uint8')
 rows,cols=np.indices((40,40));shape=(rows+cols>=10)&(rows+39-cols>=10)&(39-rows+cols>=10)&(78-rows-cols>=10)
 glyph=np.random.default_rng(17).integers(40,245,(40,40,3),dtype='uint8')
 rgb[120:160,120:160][shape]=glyph[shape]
 cv2.imwrite(str(root/'source.png'),rgb[:,:,::-1]);before=(root/'source.png').read_bytes()
 boxes=[]
 for y in range(40):
  xs=np.flatnonzero(shape[y]);boxes.append([8+int(xs.min()),8+y,9+int(xs.max()),9+y])
 item={'id':'cap','role':'tap','lane_kind':2,'source_image':'source.png','crop':[112,112,168,168],
  'anchor_pixels':[28,28],'sampling_context':[[0,0,56,56]],
  'regions':[{'name':'cap','box':[8,8,48,48],'comparison_boxes':boxes,'maximum_error':.002}]}
 spec={'skin':'generated-cornered','spacing_pixels':40,'analysis_width':320,'templates':[item]}
 path=root/'spec.json';path.write_text(json.dumps(spec));bank=load_bank(build(path,root/'masked'))
 plain=copy.deepcopy(spec);plain['templates'][0]['regions'][0].pop('comparison_boxes')
 path.write_text(json.dumps(plain));rectangular=load_bank(build(path,root/'plain'))
 target=np.full_like(rgb,[190,80,120]);target[120:160,120:160][shape]=glyph[shape]
 layout={'receptor_y':.1,'note_y_max':.95,'judgment_roi':[0,0,0,0],'combo_roi':[0,0,0,0],
  'lanes':[{'x':x/320}for x in [60,100,140,180,220]]}
 detected=SkinDetector(bank,layout,320,240).detect(target)
 plain_detected=SkinDetector(rectangular,layout,320,240).detect(target)
 template=bank['templates'][0];model=next(models(template,1))
 reusable=sorted(reusable_groups({'skin_detector':{'bank_path':str(root/'plain/bank.json'),
  'contract':{'bank':rectangular['contract'],'detector':FORMAT}}},bank))
 context_is_geometry=bool(model['cap_support'][8,8]);glyph_compared=bool(model['cap_support'][8,18])
 changed=copy.deepcopy(template);changed['mask'][28,28]=False
 unknown=next(models(changed,1));unknown_compared=bool(unknown['cap_support'][28,28])
 altered=copy.deepcopy(template);altered['regions'][0]['comparison_boxes']=boxes[1:]
 reference_bound=cap_reference(bank,template)!=cap_reference(bank,altered)
 hole=copy.deepcopy(template);hole['regions'][0]['comparison_boxes']=[[8,8,48,25],[8,31,48,48],[8,25,25,31],[31,25,48,31]]
 cap_model=next(models(hole,1))
 body={'id':'body','mask':np.ones((4,4),dtype=bool),'rgb':template['rgb'][26:30,26:30],
  'anchor_pixels':[2,2],'regions':[{'name':'body','box':[0,0,4,4]}]}
 body_model=next(models(body,1))
 images=[{'lane':2,'role':'unknown','template':'cap','bounds_pixels':[0,0,56,56]},
         {'lane':2,'role':'hold_body','template':'body','bounds_pixels':[26,26,30,30]}]
 account(images,{'cap':cap_model,'body':body_model},56,56)
 excluded_body_owned='cap_subfeature'in images[1]
 spec['analysis_width']=640;path.write_text(json.dumps(spec));scaled=load_bank(build(path,root/'scaled'))
 written=scaled['templates'][0]['regions'][0]['comparison_boxes']
 errors=[];manifest=root/'masked/bank.json';document=json.loads(manifest.read_text())
 for invalid in [[],[[7,8,48,48]],[[8,8,10,10]],[[8,8,48,48.0]]]:
  bad=copy.deepcopy(document);bad['templates'][0]['regions'][0]['comparison_boxes']=invalid;manifest.write_text(json.dumps(bad))
  try:load_bank(manifest);errors.append(False)
  except ValueError:errors.append(True)
 print(json.dumps({'detected':[{'lane':d['lane'],'x':d['x'],'y':d['y'],'role':d['role']}for d in detected],
  'plain_detected':len(plain_detected),'context_is_geometry':context_is_geometry,'glyph_compared':glyph_compared,
  'unknown_compared':unknown_compared,'reference_bound':reference_bound,'invalid_rejected':errors,
  'excluded_body_owned':excluded_body_owned,
  'reusable_groups':reusable,
  'scaled_boxes_correct':written==[[v*2 for v in box]for box in boxes],
  'source_preserved':(root/'source.png').read_bytes()==before,
  'scoped_contract':'comparison_geometry'in bank['contract']and'comparison_geometry'not in rectangular['contract']}))
`;
const observed=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));

test('a complete shaped cap survives changing background without comparing its transparent corners',()=>{
 assert.deepEqual(observed.detected,[{lane:2,x:140/320,y:140/240,role:'unknown'}]);
 assert.equal(observed.plain_detected,0,'the rectangular control includes unrelated background');
 assert.equal(observed.glyph_compared,true);assert.equal(observed.context_is_geometry,false);
});
test('selected comparison pixels cannot override unknown interpolation support',()=>{
 assert.equal(observed.unknown_compared,false);
 assert.equal(observed.excluded_body_owned,false,'known context in a geometry hole cannot explain an unowned body');
});
test('comparison geometry survives source extraction and binds its own contract and cap identity',()=>{
 assert.equal(observed.scaled_boxes_correct,true);assert.equal(observed.source_preserved,true);
 assert.equal(observed.reference_bound,true);assert.equal(observed.scoped_contract,true);
 assert.deepEqual(observed.reusable_groups,['body'],'changed comparison geometry invalidates cap measurements');
 assert.deepEqual(observed.invalid_rejected,[true,true,true,true]);
});
