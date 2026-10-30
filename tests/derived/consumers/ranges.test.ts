import test from 'node:test';import assert from 'node:assert/strict';
import {timingRanges,counterFrameRanges} from '../../../src/piu_timeline/derived/ranges.ts';
const note=target_seconds=>({status:'estimated',target_seconds,prediction_uncertainty_seconds:.01});
const match=(note,target_seconds,lo,hi)=>({note,target_seconds,observation_lower_seconds:lo,observation_upper_seconds:hi});
test('processing conflict retains raw bracket without confirming input or bounding neighbors',()=>{
 const data={notes:[note(9),note(10),note(11)],matches:[{...match(0,9,9.01,9.02),processing_conflict:true},match(2,11,11.01,11.02)]},r=timingRanges(data).notes;
 assert.equal(r[0].status,'conflicted');assert.deepEqual(r[0].observed_input_range,[9.01,9.02]);assert.deepEqual(r[0].input_ranges,[]);assert.notEqual(r[1].status,'bounded');
});
test('delayed positive processing retains disjoint alternatives and excludes reset/MISS',()=>{
 const data={notes:[note(10)],combo_events:[{delta:1,lower_seconds:10.12,upper_seconds:10.14,reason:'ambiguous'},{delta:2,lower_seconds:10.2,upper_seconds:10.23},{delta:-5,lower_seconds:10,upper_seconds:10.02}],judgment_events:[{label:'MISS',lower_seconds:10,upper_seconds:10.02}]},r=timingRanges(data);
 assert.equal(r.notes[0].status,'possible');assert.deepEqual(r.notes[0].input_ranges,[[10.12,10.14],[10.2,10.23]]);assert.equal(r.notes[0].alternatives.length,2);assert.deepEqual(r.counts,{possible:1});assert.ok(!Object.hasOwn(data,'matches'));
});
test('neighbor bounds remain conditional and require nearby independent anchors',()=>{
 const d={notes:[note(9),note(10),note(11)],matches:[match(0,9,9.01,9.02),match(2,11,11.01,11.02)]},r=timingRanges(d).notes[1];
 assert.equal(r.status,'bounded');assert.deepEqual(r.input_ranges,[[9.75,10.5]]);assert.deepEqual(r.neighbor_observation_range,[9.01,11.02]);assert.deepEqual(r.anchors,[0,2]);assert.ok(r.condition.includes('do not establish a press'));
 d.notes[2]=note(15);d.matches[1]=match(2,15,15.01,15.02);assert.equal(timingRanges(d).notes[1].status,'unknown');
});
test('MISS cannot acquire a press from nearby positive evidence',()=>{
 const r=timingRanges({notes:[note(10)],miss_candidates:[{note:0}],combo_events:[{delta:1,lower_seconds:10,upper_seconds:10.02}]}).notes[0];assert.equal(r.status,'possible_miss');assert.deepEqual(r.input_ranges,[]);
});
test('display correction changes search but preserves original observation times',()=>{
 const d={notes:[note(10)],display_delay_correction_ms:200,judgment_events:[{label:'GREAT',lower_seconds:10.6,upper_seconds:10.62}]};assert.deepEqual(timingRanges(d).notes[0].input_ranges,[[10.6,10.62]]);d.display_delay_correction_ms=0;assert.equal(timingRanges(d).notes[0].status,'unknown');
});
test('exact association retains aggregate bracket without extra alternatives',()=>{
 const r=timingRanges({notes:[note(10)],matches:[match(0,10,9.8,10.2)]}).notes[0];assert.equal(r.status,'matched');assert.deepEqual(r.input_ranges,[[9.8,10.2]]);
});
test('native counter changes keep source PTS and reject reset, low confidence and long gaps',()=>{
 const frames=[[1,5,.99],[1.01,null,0],[1.02,6,.9],[1.03,4,.95],[2.1,7,.99],[2.15,8,.2],[2.2,8,.9]].map(([playback_seconds,combo,combo_confidence])=>({playback_seconds,source_pts_seconds:playback_seconds+100,combo,combo_confidence})),r=counterFrameRanges(frames);
 assert.deepEqual(r.map(e=>[e.before,e.after]),[[5,6],[7,8]]);assert.deepEqual(r[0].source_pts_seconds,[101,101.02]);assert.deepEqual([r[0].lower_seconds,r[0].upper_seconds],[1,1.02]);
});
test('confirmed brackets are clipped without discarding original observations',()=>{
 const d={notes:[note(10)],matches:[match(0,10,9,11)]},r=timingRanges(d).notes[0];assert.deepEqual(r.input_ranges,[[9.75,10.5]]);assert.deepEqual(r.observed_input_range,[9,11]);assert.equal(d.matches[0].observation_lower_seconds,9);
 d.matches[0]=match(0,10,10.501,10.52);const f=timingRanges(d).notes[0];assert.deepEqual(f.input_ranges,[]);assert.equal(f.status,'unknown');assert.equal(f.reason,'outside_association_window');
});
test('possible input uses only the intersection with the original bracket',()=>{
 const r=timingRanges({notes:[note(10)],combo_events:[{delta:1,lower_seconds:9,upper_seconds:11}]}).notes[0];assert.deepEqual(r.input_ranges,[[9.75,10.5]]);assert.equal(r.alternatives[0].lower_seconds,9);assert.equal(r.alternatives[0].upper_seconds,11);
});
