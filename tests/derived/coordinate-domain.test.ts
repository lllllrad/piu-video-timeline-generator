import test from 'node:test';
import assert from 'node:assert/strict';
import {coordinateReferenceScene,nativeScene} from './fixtures.ts';
import {fit} from '../../src/piu_timeline/derived/beats/coordinates.ts';
import {clip,targetRange} from '../../src/piu_timeline/derived/beats/line_bounds.ts';
import {chooseRow} from '../../src/piu_timeline/derived/beats/recovery.ts';
import {attributedHeads} from '../../src/piu_timeline/derived/beats/spacing.ts';

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
