import test from 'node:test';
import assert from 'node:assert/strict';
import {coordinateReferenceScene,nativeScene} from './fixtures.ts';
import {fit,prepare} from '../../src/piu_timeline/derived/beats/coordinates.ts';
import {clip,targetRange} from '../../src/piu_timeline/derived/beats/line_bounds.ts';
import {chooseRow,recover,validateReferences} from '../../src/piu_timeline/derived/beats/recovery.ts';
import {attributedHeads} from '../../src/piu_timeline/derived/beats/spacing.ts';
import {inputNotes} from '../../src/piu_timeline/derived/holds/input.ts';

for(const spacing of [20,40,80])test(`all reference bands stay enforced at spacing ${spacing}`,()=>{
 const s=coordinateReferenceScene(spacing),before=structuredClone(s.references),model=fit(s.references,spacing);
 assert.ok(model,'a feasible line must not be lost because a median estimate misses a bound');
 assert.ok(model.coordinate_domain.vertices.length);
 assert.ok(clip(clip(model.coordinate_domain.vertices,0,s.intercept,0),.75,s.intercept+.75*s.velocity,0).length,
  'the independently generated true line must remain feasible');
 for(const [v,b] of model.coordinate_domain.vertices)for(const r of s.references)
  assert.ok(Math.abs(b+v*(r.target_seconds-model.origin_seconds)-r.offset)<=s.error+1e-7);
 const truth=.9,offset=s.intercept+s.velocity*(truth-.5),range=targetRange(model,offset,.0375*spacing);
 assert.ok(range[0]<=truth&&truth<=range[1]);assert.deepEqual(s.references,before);
 const scale=spacing/40,shift=2500*scale;
 const translated=fit(s.references.map(r=>({...r,target_seconds:r.target_seconds+100,offset:r.offset+shift})),spacing);
 const moved=targetRange(translated,offset+shift,.0375*spacing);
 assert.ok(Math.abs(moved[0]-100-range[0])<1e-8);assert.ok(Math.abs(moved[1]-100-range[1])<1e-8);
});

function unplacedHead(spacing=40,target=1.061,fine=true,nativeClock=false){
 const events:[number,number][]=Array.from({length:7},(_,i)=>[.5+i/8,i%5]);
 if(fine)events[6][0]+=1/128;events.push([target,0]);
 const data=nativeScene(events,spacing,60,5,{end:1.5});
 for(let i=0;i<7;i++)Object.assign(data.notes[i],{beat_reconstruction:{status:'restored',group_index:0},
  video_target_range:[events[i][0]-.001,events[i][0]+.001]});
 Object.assign(data.notes[7],{status:'excluded',reason:'shared_timing_reconstruction_failed',target_seconds:null,
  timing_reconstruction:{status:'failed',unaccepted_previous_estimate:{target_seconds:target}}});
 const groups=[{notes:[0,1,2,3,4,5,6],unconstrained_row_domains:events.slice(0,7).map(([t])=>[Math.round(t*128),Math.round(t*128)])}];
 if(nativeClock){
  Object.assign(data.notes[7],{reason:'beat_grid_conflicts_with_spatial_spacing',video_target_range:[target-.01,target+.01],
   timing_reconstruction:{status:'restored',method:'shared_scroll_clock'},beat_reconstruction:{status:'failed',group_index:1}});
  groups.push({notes:[7],unconstrained_row_domains:[[0,0]]});
 }
 const result=recover(data.notes,prepare(data,spacing,true),[[0,3,120]],0,0,0,groups,[0,0],spacing,data.scroll_motion);
 return {data,result};
}
for(const spacing of [20,40,80])test(`continuous native timing survives ambiguous musical rows at spacing ${spacing}`,()=>{
 const {data,result}=unplacedHead(spacing),head=data.notes[7];
 assert.equal(result[7].status,'failed');assert.equal(result[7].reason,'ambiguous_native_coordinate_rows');
 assert.equal(result[7].native_interval_status,'restored');assert.equal(head.status,'excluded');assert.equal(head.target_seconds,null);
 assert.equal(head.timing_reconstruction.status,'restored');assert.equal(head.beat_reconstruction.status,'failed');
 assert.ok(head.video_target_range[0]<1.061&&head.video_target_range[1]>1.061);
 assert.deepEqual(validateReferences(data.notes,result),[]);
 const native=inputNotes(data.notes)[7];assert.equal(native.status,'estimated');
 assert.equal(native.beat_reconstruction.status,'failed');assert.deepEqual(native.points,head.points);
});
test('invalid final references revoke a continuous native interval',()=>{
 for(const mode of ['excluded','changed-time']){
  const {data,result}=unplacedHead();
  if(mode==='excluded')data.notes[0].status='excluded';else data.notes[0].target_seconds+=.001;
  const warnings=validateReferences(data.notes,result);
  assert.equal(warnings[0].reason,'native_coordinate_reference_failed_validation');
  assert.equal(result[7].native_interval_status,'failed');assert.equal(data.notes[7].timing_reconstruction.status,'failed');
  assert.equal(inputNotes(data.notes)[7].status,'excluded');
 }
});
test('incompatible native models do not supply a usable continuous interval',()=>{
 const model=fit(coordinateReferenceScene().references,40);
 const result=chooseRow([{model,range:[1,1.01]},{model,range:[1.02,1.03]}],[[0,3,120]],0,0);
 assert.equal(result.reason,'incompatible_native_coordinate_models');assert.equal(result.native_target_range,undefined);
});
test('invalid references also revoke a previously unique coordinate-derived beat target',()=>{
 const {data,result}=unplacedHead(40,1.0625,false);
 assert.equal(result[7].status,'restored');assert.equal(data.notes[7].timing_reconstruction.status,'restored');
 data.notes[0].target_seconds+=.001;validateReferences(data.notes,result);
 assert.equal(result[7].status,'failed');assert.equal(data.notes[7].timing_reconstruction.status,'failed');
 assert.equal(inputNotes(data.notes)[7].status,'excluded');
});
test('a rejected coordinate model cannot erase a valid independent native clock',()=>{
 const {data,result}=unplacedHead(40,1.0625,false,true);
 assert.equal(result[7].status,'restored');
 data.notes[0].status='excluded';validateReferences(data.notes,result);
 const head=data.notes[7];
 assert.equal(result[7].status,'failed');assert.equal(result[7].native_interval_status,'original_clock_retained');
 assert.equal(head.beat_reconstruction.status,'failed');assert.equal(head.timing_reconstruction.method,'shared_scroll_clock');
 assert.deepEqual(head.video_target_range,[1.0525,1.0725]);assert.equal(inputNotes(data.notes)[7].status,'estimated');
});
test('inconsistent simultaneous references and unidentifiable positive motion fail',()=>{
 const s=coordinateReferenceScene();
 const contradictory=[...s.references,{...s.references[0],note:9,offset:s.references[0].offset+2.01*s.error}];
 assert.equal(fit(contradictory,40),null);
 assert.equal(fit(s.references.map(r=>({...r,offset:100})),40),null);
});
test('two individually possible heads can still have no joint coordinate model',()=>{
 const s=coordinateReferenceScene(40,[0,0,0,0,0,0,0]),model=fit(s.references,40);
 const target=1,offset=s.intercept+s.velocity*(target-.5),positions=[offset-1.2,offset+1.2];
 for(const x of positions)assert.ok(clip(model.coordinate_domain.vertices,target-model.origin_seconds,x,1).length);
 const [rejected,proof]=attributedHeads(0,1,nativeScene([[target,0],[target,1]]).notes,
  [{...model,chunk:0,peer_offsets_pixels:positions}]);
 assert.deepEqual(rejected,[0,1]);assert.equal(proof[0].joint_model_feasible,false);
});
test('full model uncertainty cannot be replaced by one convenient beat row',()=>{
 const s=coordinateReferenceScene(40,[0,0,0,0,0,0,0]);s.references[6].target_seconds+=1/128;
 s.references[6].offset+=s.velocity/128;
 const model=fit(s.references,40),target=1.061,offset=s.intercept+s.velocity*(target-.5);
 const point=[target-1.5/s.velocity,target+1.5/s.velocity],range=targetRange(model,offset,1.5);
 assert.throws(()=>targetRange({...model,coordinate_domain:undefined},offset,1.5),/Bounded positive/);
 const m=r=>[{model,range:r}];
 assert.equal(chooseRow(m(point),[[0,3,120]],0,0).status,'restored');
 assert.equal(chooseRow(m(range),[[0,3,120]],0,0).reason,'ambiguous_native_coordinate_rows');
 for(const t of [1.0546875,1.0625])assert.ok(clip(model.coordinate_domain.vertices,t-model.origin_seconds,offset,1.5).length);
});
