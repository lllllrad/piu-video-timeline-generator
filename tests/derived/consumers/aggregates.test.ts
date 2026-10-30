import test from 'node:test';import assert from 'node:assert/strict';
import {recoverAggregates} from '../../../src/piu_timeline/derived/recovery.ts';
import {present} from '../../../src/piu_timeline/derived/hold_presentation.ts';
import {aggregate,note} from './fixtures.ts';
test('other press offsets cannot move aggregate target eligibility',()=>{
 const d=aggregate();d.notes.push({...note(1.5,2),prediction_uncertainty_seconds:.01});d.matches.push({note:2,target_seconds:1.5,combo_event:1,observation_lower_seconds:1.9,observation_upper_seconds:1.92});
 const [m,r]=recoverAggregates(d);assert.deepEqual(r,[1]);assert.equal(m.find(m=>m.note===1).observation_upper_seconds,1.08);
 const a=structuredClone(d);a.matches=a.matches.slice(1);a.notes.push(...[.6,.7].map((t,i)=>({...d.notes[0],target_seconds:t,lane:i+3})));assert.deepEqual(recoverAggregates(a)[1],[]);d.display_delay_correction_ms=400;assert.deepEqual(recoverAggregates(d)[1],[]);
});
test('unowned body-image summaries do not invent continuous receptor holds',()=>{
 const d=aggregate();Object.assign(d,{native_body_risk_available:true,unsupported_intervals:[]});d.hold_analysis.unresolved_tracks=[{visible_start_seconds:.1,visible_end_seconds:2,failure_detail:'skin_body_images_without_complete_endpoint_ownership',image_evidence:[.1,2].map(playback_seconds=>({role:'hold_body',playback_seconds}))}];
 const before=structuredClone(d),[m,r]=recoverAggregates(d);assert.deepEqual(r,[1]);assert.deepEqual(d,before);assert.equal(m[1].aggregate_body_risk_basis,'native_receptor_body_regions');
 for(const kind of ['active','unavailable','connected','missing']){const a=structuredClone(d);
if(kind==='active')a.unsupported_intervals=[{start_seconds:1,end_seconds:1.1}];
if(kind==='unavailable')a.native_body_risk_available=false;
if(kind==='connected')a.hold_analysis.unresolved_tracks[0].failure_detail='unresolved_connected_body';
if(kind==='missing')delete a.hold_analysis.unresolved_tracks[0].image_evidence;
assert.deepEqual(recoverAggregates(a)[1],[]);
}
});
test('distinct chart rows can be pressed together with independent onsets',()=>{
 const d=aggregate();d.matches=[];d.judgment_events=[];Object.assign(d.combo_events[0],{lower_seconds:1.04,upper_seconds:1.06});d.hold_analysis.receptor_runs.forEach(r=>Object.assign(r,{onset_range:[1.04,1.06],onset_source_pts_seconds:[101.04,101.06],start_seconds:1.06,end_seconds:1.1}));
 const [m,r]=recoverAggregates(d);assert.deepEqual(r,[0,1]);assert.ok(m.every(m=>m.observation_lower_seconds===1.04&&m.observation_upper_seconds===1.06));
});
test('independent taps retain aggregate bracket and existing narrow word grade',()=>{
 const d=aggregate(),before=structuredClone(d),[m,r]=recoverAggregates(d);
assert.deepEqual(d,before);
assert.deepEqual(r,[1]);
assert.equal(m[0].observation_lower_seconds,1.01);
assert.equal(m[0].observation_upper_seconds,1.02);
assert.equal(m[0].judgment_label,'GREAT');
assert.equal(m[0].evidence_source,'combo+lane_onset+judgment');
assert.equal(m[1].observation_lower_seconds,1);
assert.equal(m[1].observation_upper_seconds,1.08);
assert.deepEqual(m[1].aggregate_lane_onset_source_pts_seconds,[101.06,101.08]);
assert.ok(!Object.hasOwn(m[1],'judgment_label'));
assert.ok(m.every(m=>m.combo_event===0&&m.aggregate_row_count===2));

 const view=present(d);assert.deepEqual(new Set(view.matches.map(m=>m.note)),new Set([0,1]));assert.equal(view.combo_events[0].status,'matched');assert.equal(view.combo_events[0].reason,'aggregate_counter_with_exclusive_lane_onsets');assert.equal(view.coverage.timed_note_heads,2);
});
test('aggregate 100ms limit is inclusive and not widened',()=>{const d=aggregate();d.combo_events[0].upper_seconds=1.1;const [m,r]=recoverAggregates(d);assert.deepEqual(r,[1]);assert.equal(m[1].observation_upper_seconds,1.1);d.combo_events[0].upper_seconds+=.00001;assert.deepEqual(recoverAggregates(d)[1],[]);});
for(const kind of ['static','unknown','single','missing','shared','owned'])test(`invalid onset cannot fill aggregate counter: ${kind}`,()=>{
 const d=aggregate(),r=d.hold_analysis.receptor_runs;
if(kind==='static')r[1].onset_range=null;
if(kind==='unknown')r[1].lit=null;
if(kind==='single')r[1].frames=1;
if(kind==='missing')r.pop();
if(kind==='shared'){d.notes[1].lane=0;
r[0].onset_range=[1,1.08];
}if(kind==='owned'){d.notes.push({...note(1.5,1),prediction_uncertainty_seconds:.01});
d.matches.push({note:2,target_seconds:1.5,combo_event:2,observation_lower_seconds:1.06,observation_upper_seconds:1.08});
}assert.deepEqual(recoverAggregates(d)[1],[]);

});
for(const kind of ['hold','body','miss','possible_miss','extra','chord','wrong_count','gap','counter','word','uncertain'])test(`ambiguous aggregate stays unresolved: ${kind}`,()=>{
 const d=aggregate();
if(kind==='hold')d.hold_analysis.holds=[{start_range:[.5,.6],end_range:[2,2.1]}];
if(kind==='body')d.hold_analysis.unresolved_tracks=[{visible_start_seconds:.7,visible_end_seconds:.9}];
if(kind==='miss')d.judgment_events.push({label:'MISS',lower_seconds:1.03,upper_seconds:1.04});
if(kind==='possible_miss')d.miss_candidates=[{note:1}];
if(['extra','chord'].includes(kind))d.notes.push({...note(kind==='extra'?1.05:1.1,2),prediction_uncertainty_seconds:.01});

 if(kind==='wrong_count')d.combo_events[0].delta=3;if(kind==='gap')d.combo_events[0].lower_seconds=.8;if(kind==='counter')d.matches[0].combo_event=2;if(kind==='uncertain')d.notes[1].prediction_uncertainty_seconds=.08;
 if(kind==='word'){d.notes.push({...note(1.4,2),prediction_uncertainty_seconds:.01});d.matches.push({note:2,target_seconds:1.4,combo_event:null,judgment_event:1,observation_lower_seconds:1.04,observation_upper_seconds:1.05});}assert.deepEqual(recoverAggregates(d)[1],[]);
});
test('competing aggregate refreshes cannot claim the same taps',()=>{const d=aggregate();d.combo_events.push({...d.combo_events[0]});assert.deepEqual(recoverAggregates(d)[1],[]);});
