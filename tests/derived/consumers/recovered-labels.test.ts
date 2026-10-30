import test from 'node:test';import assert from 'node:assert/strict';
import {attachRecoveredLabels} from '../../../src/piu_timeline/derived/labels.ts';
import {present} from '../../../src/piu_timeline/derived/hold_presentation.ts';
import {recovered} from './fixtures.ts';
test('unique refresh labels recovered chord, preserves brackets and is idempotent',()=>{
 const d=recovered();d.matches.push({...d.matches[0],note:1});const before=structuredClone(d),r=attachRecoveredLabels(d);assert.deepEqual(d,before);assert.deepEqual(r.matches.map(m=>m.judgment_label),['PERFECT','PERFECT']);assert.equal(r.judgment_events[0].anchor_combo_event,0);
 for(const [i,m]of r.matches.entries()){for(const k of Object.keys(before.matches[i]))if(k!=='evidence_source')assert.deepEqual(m[k],before.matches[i][k]);assert.equal(m.evidence_source,'combo+lane_onset+judgment');assert.equal(m.judgment_label_source,'recovered_synchronized_refresh');}assert.deepEqual(attachRecoveredLabels(r),r);
});
for(const key of ['judgment_events','combo_events'])test(`competing native refresh keeps grade unknown: ${key}`,()=>{
 const d=recovered();d[key].push({...d[key][0],status:key==='judgment_events'?'candidate':'excluded',...(key==='combo_events'?{reason:'ambiguous_note_or_combo_association'}:{})});assert.ok(!Object.hasOwn(attachRecoveredLabels(d).matches[0],'judgment_label'));
});
test('owned word refresh cannot be stolen by recovered row',()=>{const d=recovered();d.matches.push({note:1,combo_event:null,judgment_event:0,judgment_label:'PERFECT',target_seconds:1.04});assert.ok(!Object.hasOwn(attachRecoveredLabels(d).matches[0],'judgment_label'));});
for(const kind of ['unproven','aggregate','separated','miss','invalid','anchor','persistent'])test(`unproven grade remains unknown: ${kind}`,()=>{
 const d=recovered();
if(kind==='unproven')delete d.matches[0].recovery_method;
if(kind==='aggregate')d.combo_events[0].delta=2;
if(kind==='separated')d.matches.push({...d.matches[0],note:1,target_seconds:1.1});
if(kind==='miss')d.judgment_events[0].label='MISS';
if(kind==='invalid')d.judgment_events[0].detection_status='excluded';
if(kind==='anchor')d.judgment_events[0].anchor_combo_event=1;
if(kind==='persistent')d.judgment_events=[];
assert.ok(!Object.hasOwn(attachRecoveredLabels(d).matches[0],'judgment_label'));

});
test('hold view reconnects only after independent lane recovery',()=>{
 const d=recovered(),m=d.matches.pop();Object.assign(m,{combo_lower_seconds:1,combo_upper_seconds:1.017});Object.assign(d,{notes:[{lane:0,status:'estimated',target_seconds:1.01}],deferred_matches:[m],hold_analysis:{holds:[],receptor_runs:[]}});assert.deepEqual(present(d).matches,[]);
 d.hold_analysis.receptor_runs=[{lane:0,lit:true,frames:3,previous_seconds:.99,start_seconds:1.017,end_seconds:1.05}];const before=structuredClone(d),r=present(d);assert.deepEqual(d,before);assert.equal(r.matches[0].judgment_label,'PERFECT');assert.equal(r.matches[0].observation_upper_seconds,1.017);assert.equal(r.judgment_events[0].status,'corroborating');
});
