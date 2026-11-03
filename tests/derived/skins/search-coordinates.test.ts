import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {contracts} from '../../../src/piu_timeline/derived/contracts.ts';
import {imagePosition} from '../../../src/piu_timeline/derived/coordinates/measurements.ts';
import {measurementInput} from '../../../src/piu_timeline/derived/native_gaps.ts';

const native=String.raw`
import json,numpy as np
from piu_timeline.play.skins.coordinates import registered_comparison
templates={name:{'lane_kind':0,'mask':np.ones((40,20)),
 'regions':[{'name':'cap','maximum_error':.015}]}for name in ('a','b')}
bank={'anchor_registrations':{name:{'coordinate_uncertainty_pixels':1,
 'center_offset_y_pixels':0}for name in templates}}
checked=0
for scale in (.25,.5,1,2):
 for fraction in (.01,.24,.49,.51,.76,.99):
  # Known continuous scene translation, independently rounded by target search.
  center=100+fraction;row=round(center)
  image={'template':'a','y':row/400,'region_errors':{'cap':0},
   'reference_scale_y':scale,'sampling_origin_pixels':[0,0]}
  result,conflict=registered_comparison(image,bank,templates,0,row,400,scale)
  error=result['native_cap_coordinate_uncertainty_pixels']
  assert abs(result['native_y_pixels']-center)<=error
  assert error==scale+.5 and conflict is None
  checked+=1
# Source-reference variants may differ within independent source and target errors.
image={'template':'a','y':100/400,'region_errors':{'cap':0},
 'reference_scale_y':.5,'sampling_origin_pixels':[0,0]}
image['alternatives']=[{**image,'template':'b','y':101.25/400}]
result,conflict=registered_comparison(image,bank,templates,0,100,400,.5)
assert conflict is None
image['alternatives'][0]['y']=103/400
_,conflict=registered_comparison(image,bank,templates,0,100,400,.5)
assert conflict is not None
print(json.dumps({'checked':checked,'sample':{'time':1,'source_pts_seconds':81,
 'native_y_pixels':100,'template':'a','sampling_origin_pixels':[0,0],**result}}))
`;

test('target-grid rounding is separate from scaled source uncertainty and reaches TS consumers',()=>{
 const {checked,sample}=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',native],{encoding:'utf8'}));
 assert.equal(checked,24);
 const position=imagePosition(sample,100,contracts.image_coordinates);
 assert.equal(position.kind,'native_cap_center');
 if(position.kind==='native_cap_center')assert.equal(position.uncertaintyPixels,1);
 const transported=measurementInput({format:contracts.image_coordinates,notes:[{note:0,
  coordinate_method:'native_image_anchors',observations:[sample]}]});
 assert.deepEqual(imagePosition(transported.notes[0].observations[0],100,transported.format),position);
 for(const bad of[{...sample,native_cap_sampling_uncertainty_pixels:1},
  {...sample,native_cap_coordinate_uncertainty_pixels:.5},
  {...sample,sampling_origin_pixels:undefined}])
  assert.equal(imagePosition(bad,100,contracts.image_coordinates).kind,'unavailable');
 assert.equal(imagePosition(sample,100,{native_cap_registration:contracts.native_anchor}).kind,'unavailable');
});
