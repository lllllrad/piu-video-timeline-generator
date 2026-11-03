import test from 'node:test';
import assert from 'node:assert/strict';
import {choose} from '../../../src/piu_timeline/derived/skins/selection.ts';
function candidate(skin='generated',revision='one'){
 return {selection:{skin,revision},observations:Array.from({length:6},(_,i)=>Array.from({length:3},(_,lane)=>({
  window:Math.floor(i/2),source_pts_seconds:30+i*.08,lane,y:.5-i*.01,quality:.95,method:'skin_image',template_role:'tap',classification_status:'full_pattern'}))).flat()};
}
test('a uniquely supported skin is selected from independent images without modifying observations',()=>{
 const candidates=[candidate(),{...candidate('other'),observations:[]}],before=structuredClone(candidates),r=choose(candidates);
 assert.equal(r.status,'selected');assert.deepEqual(r.selection,{skin:'generated',revision:'one'});assert.deepEqual(candidates,before);
});
for(const mode of['empty','one_window','one_direction','weak','body_only','repeated_frame'])test(`unsupported image identification stays unresolved: ${mode}`,()=>{
 const c=candidate();
 if(mode==='empty')c.observations=[];
 for(const o of c.observations){
  if(mode==='one_window')o.window=0;if(mode==='one_direction')o.lane=0;
  if(mode==='weak')o.quality=.1;if(mode==='body_only')o.template_role='hold_body';
  if(mode==='repeated_frame')o.source_pts_seconds=30;
 }
 assert.equal(choose([c]).status,'unresolved');
});
for(const sameSkin of[false,true])test(`multiple qualified banks cannot select a convenient winner: same skin=${sameSkin}`,()=>{
 const r=choose([candidate(),candidate(sameSkin?'generated':'other','two')]);
 assert.equal(r.status,'unresolved');assert.equal(r.reason,'ambiguous_skin_images');
});
test('skin identity can be supported while cap roles remain unknown',()=>{
 const c=candidate();c.observations.forEach(o=>o.classification_status='cap_only');
 const r=choose([c]);assert.equal(r.status,'selected');assert.equal(r.evidence[0].full_patterns,0);
});
test('duplicate cap records cannot inflate the independent support count',()=>{
 const c=candidate(),caps=c.observations.slice(0,4).map((o,i)=>({...o,window:i%3,source_pts_seconds:30+i*.1,lane:i%3,y:.5}));
 c.observations=caps.flatMap(o=>Array.from({length:5},()=>({...o})));
 assert.equal(choose([c]).status,'unresolved');
});
