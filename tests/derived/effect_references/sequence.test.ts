import test from 'node:test';
import assert from 'node:assert/strict';
import {regions} from '../../../src/piu_timeline/derived/effect_references/regions.ts';
import {evolution,changes} from '../../../src/piu_timeline/derived/effect_references/temporal.ts';
import {variants,recognize} from '../../../src/piu_timeline/derived/effect_references/bank.ts';
import {align,sequence,compare} from '../../../src/piu_timeline/derived/effect_references/model.ts';
import type {Patch,Capture} from '../../../src/piu_timeline/derived/effect_references/model.ts';
const solid=(n:number):Patch=>({rgb:new Uint8Array(1521*3).fill(n),visible:new Uint8Array(1521).fill(1)});
test('local residual contamination is bounded and broad disagreement is retained',()=>{
 const ref=solid(50),query=solid(50);
 for(let y=0;y<12;y++)for(let x=0;x<12;x++)query.rgb.fill(230,(y*39+x)*3,(y*39+x)*3+3);
 const cleaned=regions(query,ref);
 assert.ok(cleaned.removed.length);assert.equal(compare(cleaned.patch,ref),0);
 assert.ok(cleaned.patch.visible.reduce((a,b)=>a+b,0)>=1521*.80);
 assert.equal(query.visible.reduce((a,b)=>a+b,0),1521);
 const broad=regions(solid(220),ref);assert.equal(broad.removed.length,0);assert.ok(compare(broad.patch,ref)>.5);
});
test('RGB evolution distinguishes forward from reversed and static stages',()=>{
 const q=[30,70,110,150,180].map(solid);
 assert.equal(evolution(q,q).error,0);
 assert.ok(evolution(q,[...q].reverse()).error>.05);
 assert.ok(evolution(q,q).reference_change>.1);
 assert.equal(evolution(q,q.map(()=>solid(30))).reference_change,0);
});
test('actual reference variants require three supporting training sequences',()=>{
 const a=[30,60,90,120,150,180,200].map(solid);
 assert.equal(variants([{id:'one',patches:a},{id:'two',patches:a}]).length,0);
 const selected=variants(['one','two','three'].map(id=>({id,patches:a})));
 assert.ok(selected.length>0);assert.ok(selected.every(s=>s.support===3));
});
function capture(values:number[]) {
 const frames=values.map((_,i)=>({offset:i,pts:100+i/60,time:i/60,crop:[0,0,47,47],envelopes:[]}));
 const pixels=new Uint8Array(values.length*47*47*3);
 values.forEach((v,i)=>pixels.fill(v,i*47*47*3,(i+1)*47*47*3));
 const e={id:'query',kind:0,lane:0,marker:8/60,frames};
 const c:Capture={events:[e],pixels,exclusions:new Uint8Array(values.length*47*47)};
 return {c,e};
}
test('appearance agreement without ordered change remains phase unresolved',()=>{
 const {c,e}=capture(Array(34).fill(70)),ref=sequence(c,e);
 const result=recognize(c,e,[{id:'reference',patches:ref}]);
 assert.equal(result.status,'appearance_only_phase_unresolved');
 assert.equal(result.order_margin,0);
});
test('native-frame search recovers a delayed image sequence beyond the old 67ms range',()=>{
 const {c,e}=capture(Array.from({length:34},(_,i)=>20+i*5));
 const ref=sequence(c,e,.117),fit=align(c,e,ref);
 assert.ok(fit);assert.equal(fit.error,0);assert.ok(fit.offset>.1);
 const ps=[solid(30),solid(100)];
 ps[0].frame={offset:0,pts:10,time:1,crop:[],envelopes:[]};ps[1].frame={offset:1,pts:10.017,time:1.017,crop:[],envelopes:[]};
 assert.deepEqual(changes(ps)[0].source_pts,[10,10.017]);assert.deepEqual(changes(ps)[0].bracket,[1,1.017]);
});
