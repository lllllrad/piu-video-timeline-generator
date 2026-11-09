import test from 'node:test';
import assert from 'node:assert/strict';
import {resolve,resolveMany} from '../../../src/piu_timeline/derived/skins/localization.ts';
import {imagePosition} from '../../../src/piu_timeline/derived/coordinates/measurements.ts';
import {measurementInput} from '../../../src/piu_timeline/derived/native_gaps.ts';
import {contracts} from '../../../src/piu_timeline/derived/contracts.ts';
import type {RecordData} from '../../../src/piu_timeline/derived/types.ts';

const comparison=(y:number,error:number,offset=0)=>({template:'generated-cap',comparison_index:0,
 image_y:y/400,cap_error:error,maximum_error:.015,scale_y:.5,same_cap:true,center_offset_y_pixels:offset,reference:'generated-reference',localization_pixels:{method:'visible_cap_rgb_and_vertical_contrast',
 compared_pixels:400,vertical_contrast_pixels:80,squared_rgb_error:error,vertical_contrast_error:0}});

test('a weaker positive match at a different position neither moves nor enlarges the uniquely localized center',()=>{
 for(const scale of [.25,.5,1,1.5,2])for(const delta of [.01,.5,1,2,5]){
  const best={...comparison(100,.001,10),scale_y:scale};
  const alternatives=[{...best,template:'different-pose',image_y:(100+delta)/400,cap_error:.01,comparison_index:1,localization_pixels:{...best.localization_pixels,squared_rgb_error:.01}}];
  for(const comparisons of [[best,...alternatives],[...alternatives,best]]){
   const r=resolve({height:400,raw_y:100,comparisons});
   assert.equal(r.conflict,null);
   assert.equal(r.measurement.native_y_pixels,100+10*scale);
   assert.equal(r.measurement.native_cap_coordinate_uncertainty_pixels,0);
   assert.equal(r.measurement.native_cap_projection_uncertainty_pixels,0);
   assert.ok(r.anchors.every(a=>a.uncertaintyPixels===0));
  }
 }
});

test('equal pixel support at distinct centers fails without an arbitrary projection or widened fallback anchor',()=>{
 for(const delta of [1e-8,.001,.5,1,3]){
  const r=resolve({height:400,raw_y:100,comparisons:[comparison(100,.001),comparison(100+delta,.001)]});
  assert.equal(r.conflict.reason,'image_position_ambiguous');
  assert.deepEqual(r.measurement,{});
  assert.deepEqual(r.anchors,[]);
 }
});

test('missing pixels, invisible vertical features and failed vertical contrasts cannot localize a cap',()=>{
 for(const pixels of [undefined,{...comparison(100,0).localization_pixels,vertical_contrast_pixels:0},
  {...comparison(100,0).localization_pixels,squared_rgb_error:.1},
  {...comparison(100,0).localization_pixels,vertical_contrast_error:.1}]){
  const r=resolve({height:400,raw_y:100,comparisons:[{...comparison(100,0),localization_pixels:pixels}]});
  assert.deepEqual(r.measurement,{});assert.deepEqual(r.anchors,[]);
  assert.equal(r.conflict.reason,'image_localization_pixels_unqualified');
 }
});

test('matching anchor, center convention, reference aliases and unrelated caps remain distinct',()=>{
 const sameCenter=[comparison(100,.001,10),comparison(103,.001,4)];
 const r=resolve({height:400,raw_y:100,comparisons:sameCenter});
 assert.equal(r.conflict,null);assert.equal(r.measurement.native_y_pixels,105);
 assert.equal(r.measurement.native_cap_localization.candidate_positions,1);
 const unrelated=resolve({height:400,raw_y:100,comparisons:[comparison(100,.001),{...comparison(200,0),same_cap:false}]});
 assert.equal(unrelated.measurement.native_y_pixels,100);
 const unregistered={...comparison(100,0)};delete unregistered.center_offset_y_pixels;
 assert.deepEqual(resolve({height:400,raw_y:100,comparisons:[unregistered]}).measurement,{});
});

test('the same zero-radius localization evidence survives the numerical-stage transport and rejects added budgets',()=>{
 const measurement=resolveMany([{height:400,raw_y:100,comparisons:[comparison(100,.001),comparison(103,.01)]}])[0].measurement;
 const sample:RecordData={time:1,source_pts_seconds:81,template:'generated-cap',...measurement};
 const r={format:contracts.image_coordinates,notes:[{note:0,coordinate_method:'native_image_anchors',observations:[sample]}]};
 const position=imagePosition(sample,100,r.format),wire=measurementInput(r);
 assert.equal(position.kind,'native_cap_center');
 if(position.kind==='native_cap_center')assert.equal(position.uncertaintyPixels,0);
 assert.deepEqual(imagePosition(wire.notes[0].observations[0],100,wire.format),position);
 for(const corrupt of [{...sample,native_cap_coordinate_uncertainty_pixels:.001},
  {...sample,native_cap_projection_uncertainty_pixels:2},{...sample,native_cap_sampling_uncertainty_pixels:.5},
  {...sample,native_cap_registration_status:'conflicting'},
  {...sample,native_cap_localization:{...sample.native_cap_localization,runner_up_score:.01,score_margin:1}}])
  assert.equal(imagePosition(corrupt,100,r.format).kind,'unavailable');
});
