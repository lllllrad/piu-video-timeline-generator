import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';

const script=String.raw`
import json,tempfile
from pathlib import Path
import cv2,numpy as np
from piu_timeline.play.skins.kernels import bicubic_weights
from piu_timeline.play.skins.sampling import models
from piu_timeline.play.skins.build import build
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.coverage import reference_rows
wx,pad=bicubic_weights(8,1.5,0)
mask=np.ones((8,8),dtype=bool);mask[2,1]=False
ref={'id':'cap','mask':mask,'rgb':np.full((8,8,3),100,dtype='uint8'),'anchor_pixels':[4,4],
 'regions':[{'name':'cap','box':[0,0,8,8],'maximum_error':.002}]}
model=next(m for m in models(ref,1.5)if m.get('sampling_kernel')=='bicubic'and m['sampling_phase_pixels']==[0,0])
weighted=wx@np.pad(mask.astype(float),pad)@wx.T
ctx={'id':'cap','mask':np.ones((20,20),dtype=bool),'rgb':np.full((20,20,3),100,dtype='uint8'),
 'anchor_pixels':[10,10],'regions':[{'name':'cap','box':[4,4,16,16],'maximum_error':.002}]}
def choose(r):return next(m for m in models(r,1.5)if m.get('sampling_kernel')=='bicubic'and m['sampling_phase_pixels']==[0,0])
full=choose(ctx);tight={**ctx,'mask':np.zeros((20,20),dtype=bool)};tight['mask'][4:16,4:16]=True
limited=choose(tight)
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);pixels=np.random.default_rng(9).integers(0,255,(240,320,3),dtype='uint8')
 image=root/'source.png';cv2.imwrite(str(image),pixels[:,:,::-1]);before=image.read_bytes()
 item={'id':'cap','role':'tap','lane_kind':0,'source_image':'source.png','crop':[20,30,60,70],
  'anchor_pixels':[20,20],'regions':[{'name':'cap','box':[10,10,30,30]}],'sampling_context':[[5,5,35,35]]}
 spec={'skin':'generated-context','spacing_pixels':40,'analysis_width':320,'templates':[item]}
 path=root/'spec.json';path.write_text(json.dumps(spec));bank=load_bank(build(path,root/'bank'))
 template=bank['templates'][0]
 data={'analysis_width':320,'analysis_height':240,'layout':{'receptor_y':.1,'lanes':[{'x':.1},{'x':.225}]},
  'skin_detector':{'bank_path':str(root/'bank/bank.json'),'contract':{'bank':bank['contract']}}}
 rows=reference_rows(data)['cap'];source_preserved=image.read_bytes()==before
 exact_rgb=bool(np.array_equal(template['rgb'],pixels[30:70,20:60]))
 context_written=bool(template['mask'][5,5])and not bool(template['mask'][4,4])
 manifest=root/'bank/bank.json';document=json.loads(manifest.read_text())
 document['templates'][0]['sampling_context']=[[-1,0,40,40]];manifest.write_text(json.dumps(document));invalid_bank=False
 try:load_bank(manifest)
 except ValueError:invalid_bank=True
 item['sampling_context']=[[-1,0,40,40]];path.write_text(json.dumps(spec));invalid=False
 try:build(path,root/'bad')
 except ValueError:invalid=True
 print(json.dumps({'coefficients':wx[4,pad+1:pad+5].tolist(),'weighted_unknown':float(weighted[4,4]),
  'unknown_compared':bool(model['support'][4,4]),'known_context_compared':bool(full['support'][6,6]),
  'missing_context_compared':bool(limited['support'][6,6]),'context_is_geometry':bool(full['support'][:6].any()),
  'builder_rows':rows,'context_written':context_written,'exact_rgb':exact_rgb,'source_preserved':source_preserved,'invalid_context_rejected':invalid,'invalid_bank_context_rejected':invalid_bank},allow_nan=False))
`;
const observed=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
test('bicubic source stencil uses the actual decoder coefficients',()=>{
 [-.075,.575,.575,-.075].forEach((v,i)=>assert.ok(Math.abs(observed.coefficients[i]-v)<1e-12));
});
test('negative kernel coefficients cannot turn an unknown source pixel into support',()=>{
 assert.ok(observed.weighted_unknown>1);assert.equal(observed.unknown_compared,false);
});
test('known interpolation context supports a comparison without becoming note geometry',()=>{
 assert.equal(observed.known_context_compared,true);assert.equal(observed.missing_context_compared,false);assert.equal(observed.context_is_geometry,false);
});
test('reference extraction retains declared source context while coverage stays within comparison regions',()=>{
 assert.equal(observed.context_written,true);assert.equal(observed.exact_rgb,true);assert.equal(observed.source_preserved,true);
 assert.deepEqual(observed.builder_rows,[[10,30]]);assert.equal(observed.invalid_context_rejected,true);assert.equal(observed.invalid_bank_context_rejected,true);
});
