import test from 'node:test';
import assert from 'node:assert/strict';
import {intersect} from '../../src/piu_timeline/derived/holds/extent.ts';
import {holdEndpointScene} from './fixtures.ts';

for(const scale of [.5,1,2,4])test(`registered endpoints preserve a rigid short hold across native rounding at scale ${scale}`,()=>{
  const samples=holdEndpointScene(43,scale),before=structuredClone(samples),result=intersect(samples);
  assert.equal(result.status,'consistent');assert.ok(result.length_range_pixels[0]<=43*scale&&result.length_range_pixels[1]>=43*scale);
  assert.deepEqual(samples,before);assert.deepEqual(result.source_pts_seconds,samples.map(s=>s.source_pts_seconds));
  const conflict=structuredClone(samples);conflict.at(-1).tail_y+=8*scale;
  assert.equal(intersect(conflict).status,'conflict','a real length change cannot be excused by rounding');
});
test('unknown endpoint errors cannot create a rigid body, and frame order is preserved',()=>{
  const missing=holdEndpointScene(43).map(s=>({...s,head_uncertainty:undefined}));assert.equal(intersect(missing).status,'unverified');
  const sparse=holdEndpointScene(43).slice(0,3);assert.equal(intersect(sparse).status,'unverified');
  const short=holdEndpointScene(43).map((s,i)=>({...s,time:i*.001}));assert.equal(intersect(short).status,'unverified');
  const duplicate=holdEndpointScene(43);duplicate[1].source_pts_seconds=duplicate[0].source_pts_seconds;assert.throws(()=>intersect(duplicate),/timeline/);
  const reversed=holdEndpointScene(43);reversed[1].time=reversed[0].time;assert.throws(()=>intersect(reversed),/timeline/);
});
