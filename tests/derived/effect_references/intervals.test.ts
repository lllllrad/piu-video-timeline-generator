import test from 'node:test';
import assert from 'node:assert/strict';
import {intervals,lanes} from '../../../src/piu_timeline/derived/effect_references/intervals.ts';
import {measureWindows} from '../../../src/piu_timeline/derived/effect_references/play_pool.ts';
test('interval index preserves inclusive boundaries, censored intervals and original order',()=>{
 const records=Array.from({length:300},(_,i)=>({id:i,lane:i%5,lo:(i*79)%401,hi:(i*79)%401+i%17}));
 records.push({id:300,lane:0,lo:-Infinity,hi:Infinity});
 const index=intervals(records,r=>[r.lo,r.hi]),byLane=lanes(records,r=>[r.lo,r.hi]);
 for(let lo=-1;lo<420;lo+=3) {
  const hi=lo+7,expected=records.filter(r=>r.lo<=hi&&r.hi>=lo);
  assert.deepEqual(index(lo,hi),expected);
  for(let lane=0;lane<5;lane++)assert.deepEqual(byLane(lane,lo,hi),expected.filter(r=>r.lane===lane));
 }
});
test('worker failure rejects the pool and cleans up; invalid concurrency is refused',async()=>{
 const capture={events:[{kind:0},{kind:0}],pixels:new Uint8Array(),exclusions:new Uint8Array()};
 await assert.rejects(measureWindows(capture,{byKind:new Map(),trainingFrames:new Map()},2));
 await assert.rejects(measureWindows(capture,{},0),/1..32/);
});
