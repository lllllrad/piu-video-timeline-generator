import test from 'node:test';
import assert from 'node:assert/strict';
import {aggregate,align,compare,disjoint,policy,reason,sequence} from '../../../src/piu_timeline/derived/effect_references/model.ts';
import type {Capture,Patch} from '../../../src/piu_timeline/derived/effect_references/model.ts';
function solid(value:number):Patch {
  return {rgb:new Uint8Array(39*39*3).fill(value),visible:new Uint8Array(39*39).fill(1)};
}
test('masked foreign artwork does not alter visible RGB correspondence',()=>{
  const original=solid(70),overlap=solid(70);
  for(let i=0;i<400;i++){overlap.visible[i]=0;overlap.rgb.fill(230,i*3,i*3+3);}
  assert.equal(compare(original,overlap),0);
  overlap.visible.fill(1);assert.ok(compare(original,overlap)>.1);
  overlap.visible.fill(0);assert.equal(compare(original,overlap),null);
});
test('unsupported consensus pixels stay unknown and cannot be supplied by one clean event',()=>{
  const samples=[solid(30),solid(60),solid(90)];samples[0].visible[0]=0;
  const p=aggregate(samples);
  assert.equal(p.visible[0],0);assert.equal(p.contributors[0],2);
  assert.equal(p.visible[1],1);assert.equal(p.rgb[3],60);
  assert.equal(aggregate([solid(50)]).visible.reduce((a,b)=>a+b,0),0);
});
test('saturated shared light cannot qualify as a distinct reference phase',()=>{
  assert.equal(reason(solid(250)),'saturated_shared_flash_candidate');
  assert.equal(compare(solid(250),solid(250)),null);
});
test('bounded temporal alignment recovers a known capture offset and rejects large RGB mismatch',()=>{
  const frames=Array.from({length:34},(_,i)=>({offset:i,pts:i/60,time:i/60,crop:[0,0,47,47],envelopes:[]}));
  const pixels=new Uint8Array(34*47*47*3),exclusions=new Uint8Array(34*47*47);
  for(let i=0;i<34;i++)pixels.fill(15+i*5,i*47*47*3,(i+1)*47*47*3);
  const e={id:'one',kind:0,lane:0,marker:8/60,frames};
  const c:Capture={events:[e],pixels,exclusions};
  const target=sequence(c,e,.033),fit=align(c,e,target);
  assert.ok(fit);assert.equal(fit.error,0);assert.equal(fit.offset,.033);
  const wrong=align(c,e,target.map(()=>solid(220)));
  assert.ok(wrong&&wrong.error>policy.maxError);
  assert.equal(disjoint(e,{...e,id:'other'}),false);
  assert.equal(disjoint(e,{...e,frames:frames.map(f=>({...f,pts:f.pts+10}))}),true);
});
