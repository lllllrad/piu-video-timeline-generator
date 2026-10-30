import test from 'node:test';import assert from 'node:assert/strict';
import type {RecordData} from '../../../src/piu_timeline/derived/types.ts';
import {present} from '../../../src/piu_timeline/derived/hold_presentation.ts';
import {observedTailRoles,chartProjection} from '../../../src/piu_timeline/derived/hold_projection.ts';
import {recognition,exclusions} from '../../../src/piu_timeline/derived/diagnostics.ts';
import {recognitionSegments} from '../../../src/piu_timeline/derived/hold_state.ts';
import {timingRanges} from '../../../src/piu_timeline/derived/ranges.ts';
function tails():RecordData{return {notes:[{lane:0,
status:'excluded',
reason:'shared_timing_reconstruction_failed',
target_seconds:null,
points:[[.1,
200],
[.2,
180],
[.3,
160],
[.4,
140]]},
{lane:0,
status:'estimated',
reason:null,
target_seconds:1.5,
points:[[.1,
240],
[.2,
220],
[.3,
200],
[.4,
180]]}],
matches:[{note:1,
target_seconds:1.5}],
combo_events:[],
judgment_events:[],
visual_channels:{note_types:{notes:[0,
1].map(note=>({note,
observations:[{kind:'hold'}]}))}},
hold_analysis:{holds:[],
unresolved_tracks:[{lane:0,
reason:'unresolved_hold_geometry',
visible_start_seconds:.1,
visible_end_seconds:.4,
cap_continuity:{decision:'connected_caps',
head_note:0,
tail_note:1,
connected_source_pts_seconds:Array.from({length:10},
(_,
i)=>100+i/60),
gap_source_pts_seconds:[],
weak_source_pts_seconds:[],
visible_start_seconds:.1,
visible_end_seconds:.3}}]}};
}
function held():RecordData{return {notes:[{lane:0,status:'estimated',target_seconds:9,prediction_uncertainty_seconds:.01},{lane:1,status:'estimated',target_seconds:10,prediction_uncertainty_seconds:.01}],matches:[],combo_events:[],judgment_events:[],hold_analysis:{holds:[{id:0,lane:0,head_note:0,covered_notes:[0],start_range:[9,9.02],end_range:[11,11.02],start_censored:false,end_censored:false,input:{segments:[]}}],receptor_runs:[]}};}
test('observed tail survives failed head timing without inventing a hold or press',()=>{
 const d=tails(),before=structuredClone(d),v=present(d);assert.deepEqual(d,before);assert.equal(v.notes[1].reason,'observed_hold_tail_pending_geometry');assert.deepEqual(v.matches,[]);assert.deepEqual(v.hold_analysis.holds,[]);assert.equal(v.notes[0].target_seconds,null);assert.equal(v.notes[1].target_seconds,1.5);
 const w=recognition(v,{notes:{}}).warnings;for(const reason of ['observed_hold_tail_pending_geometry','unresolved_hold_geometry'])assert.ok(w.some(w=>w.reason===reason));assert.ok(exclusions(d,v).warnings.some(w=>w.reason==='observed_hold_tail_pending_geometry'));
});
for(const kind of ['tap','weak','gap','owner'])test(`uncertain connection cannot remove a cap: ${kind}`,()=>{
 const d=tails(),p=d.hold_analysis.unresolved_tracks[0].cap_continuity;
if(kind==='tap')d.visual_channels.note_types.notes[1].observations.push({kind:'tap'});
if(kind==='weak')p.connected_source_pts_seconds=[100];
if(kind==='gap')p.gap_source_pts_seconds=[100.04];
if(kind==='owner'){d.notes.push({...d.notes[0],lane:0});
d.visual_channels.note_types.notes.push({note:2,observations:[{kind:'hold'}]});
const other=structuredClone(d.hold_analysis.unresolved_tracks[0]);
other.cap_continuity.head_note=2;
d.hold_analysis.unresolved_tracks.push(other);
}assert.deepEqual(observedTailRoles(d),[]);
});
test('failed head cannot project body without a chart anchor and must warn',()=>{
 const d=held(),h=d.hold_analysis.holds[0];d.notes[0].timing_reconstruction={status:'failed'};Object.assign(h,{start_censored:true,head_note:null,head_observation_note:0,covered_notes:[],last_body_seconds:10.9});const before=structuredClone(d),v=present(d);
 assert.deepEqual(v.hold_analysis.holds,[]);assert.equal(v.hold_analysis.unresolved_holds.length,1);const r=v.hold_analysis.unresolved_holds[0];assert.equal(r.projection_failure,'timing_reconstruction_failed');assert.equal(v.notes[r.display_note].status,'excluded');assert.equal(v.coverage.long_notes,0);assert.deepEqual(d,before);
 const w=recognition(v,{notes:{}}).warnings;for(const reason of ['hold_chart_projection_failed','hold_start_unresolved'])assert.ok(w.some(w=>w.reason===reason));
});
test('linked caps outside covered envelope cannot become extra taps',()=>{
 const d=held(),h=d.hold_analysis.holds[0];h.covered_notes=[];h.tail_note=2;d.notes.push({status:'estimated',lane:0,target_seconds:11.01,prediction_uncertainty_seconds:.01});d.matches=[{note:0,target_seconds:9.01,combo_event:0,observation_lower_seconds:9,observation_upper_seconds:9.02}];const before=structuredClone(d),v=chartProjection(d);
 assert.equal(v.notes.length,3);assert.equal(v.notes[0].note_type,'hold');assert.equal(v.notes[2].status,'excluded');assert.deepEqual(v.hold_analysis.holds[0].covered_notes,[0,2]);assert.ok(present(d).matches.every(m=>![0,2].includes(m.note)));assert.deepEqual(d,before);
});
test('preheld lane counts without inventing onset at visual head',()=>{
 const times=[8.9,8.95,9,9.05,9.1,9.15,9.2],frames=times.map(t=>({playback_seconds:t,source_pts_seconds:t+10,receptor_lit:[true]})),h={lane:0,start_range:[9,9.01],end_range:[9.2,9.21],start_censored:false,last_body_seconds:9.2},state=recognitionSegments(frames,times,h,{} as any);
 assert.deepEqual(state.recognition_envelope,[9,9.2]);assert.equal(state.press_range,null);const d=held();d.hold_analysis.holds[0].input=state;const r=timingRanges(present(d)).notes[0];assert.equal(r.status,'hold_state');assert.equal(r.input_requirement,'held_state');assert.equal(r.requires_head_press,false);assert.equal(r.press_range,null);
});
