import test from 'node:test';
import assert from 'node:assert/strict';
import {synchronizedRefreshes} from '../../../src/piu_timeline/derived/association.ts';
import {mergeJudgments,labelCounterFrames} from '../../../src/piu_timeline/derived/labels.ts';
const word=(label:string,t=1)=>({label,lower_seconds:t,upper_seconds:t+.016,status:'candidate',detection_status:'candidate'});
const counter=()=>({delta:1,lower_seconds:1,upper_seconds:1.016,status:'matched'});
for(const label of ['PERFECT','GREAT','GOOD','BAD','MISS'])test(`combo increases can corroborate only PERFECT/GREAT: ${label}`,()=>{
 assert.deepEqual(synchronizedRefreshes({combo_events:[counter()]},[word(label)]),['PERFECT','GREAT'].includes(label)?[[0,0]]:[]);
});
test('GOOD is independently matched without a combo update',()=>{
 const d={notes:[{lane:0,status:'estimated',target_seconds:1,prediction_uncertainty_seconds:.01}],matches:[],combo_events:[],coverage:{}};
 const r=mergeJudgments(d,[word('GOOD')]);assert.equal(r.matches.length,1);
 assert.equal(r.matches[0].judgment_label,'GOOD');assert.equal(r.matches[0].combo_event,null);assert.equal(r.matches[0].evidence_source,'judgment');
});
test('a GOOD cannot relabel the row already owning a positive combo update',()=>{
 const d={notes:[{lane:0,status:'estimated',target_seconds:1,prediction_uncertainty_seconds:.01}],
 matches:[{note:0,target_seconds:1,combo_event:0,combo_lower_seconds:1,combo_upper_seconds:1.016}],combo_events:[counter()],coverage:{}};
 const r=mergeJudgments(d,[word('GOOD')]);assert.equal(r.matches.length,1);assert.equal(r.matches[0].judgment_label,undefined);
 const frames=[1.016,1.033].map(t=>({playback_seconds:t,source_pts_seconds:80+t,label:'GOOD',confidence:.99}));
 labelCounterFrames(r,frames);assert.equal(r.matches[0].judgment_label,undefined);
});
