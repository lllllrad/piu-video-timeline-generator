import test from 'node:test';
import assert from 'node:assert/strict';
import type {RecordData} from '../../src/piu_timeline/derived/types.ts';
import {nativeScene} from './fixtures.ts';
import {mergeJudgments} from '../../src/piu_timeline/derived/labels.ts';
import {present} from '../../src/piu_timeline/derived/hold_presentation.ts';
import {crossing} from '../../src/piu_timeline/derived/clocks.ts';
import {associate} from '../../src/piu_timeline/derived/association.ts';
import {recoverRows} from '../../src/piu_timeline/derived/recovery.ts';

function scene(spacing=40,fps=60,chord=false,delay=0):RecordData{
 const d=nativeScene(chord?[[1,0],[1,1]]:[[1,0]],spacing,fps,5,{end:1.4});
 d.notes.forEach(n=>Object.assign(n,{target_seconds:1-.25/fps,prediction_uncertainty_seconds:.5/fps,type_status:'tap',timing_reconstruction:{status:'restored'}}));
 const lo=1+.044+delay,hi=lo+1/fps;
 return {...d,display_delay_correction_ms:delay*1000,matches:[],combo_events:[{status:'excluded',reason:'ambiguous_note_or_combo_association',delta:1,lower_seconds:lo,upper_seconds:hi}],
  judgment_events:[{label:'PERFECT',delta:1,detection_status:'candidate',lower_seconds:lo,upper_seconds:hi}],
  hold_analysis:{holds:[],unresolved_tracks:[],receptor_runs:[]},median_frame_interval_seconds:1/fps};
}
for(const spacing of[20,40,80])for(const fps of[30,60,120])for(const chord of[false,true])test(`bounded synchronized refresh: spacing=${spacing}, fps=${fps}, chord=${chord}`,()=>{
 const d=scene(spacing,fps,chord),before=structuredClone(d);
 assert.deepEqual(associate(d.notes,[{...d.combo_events[0],status:'candidate'}]),[],'representative target alone misses the measured refresh');
 const[matches,recovered]=recoverRows(d);
 assert.equal(matches.length,chord?2:1);assert.deepEqual(recovered,chord?[0,1]:[0]);
 for(const m of matches){
  assert.equal(m.recovery_method,'exclusive_bounded_target_with_synchronized_refreshes');
  assert.ok(m.association_target_range[0]<=1&&m.association_target_range[1]>=1);
  assert.equal(m.target_seconds,d.notes[m.note].target_seconds);
  assert.deepEqual([m.observation_lower_seconds,m.observation_upper_seconds],[d.combo_events[0].lower_seconds,d.combo_events[0].upper_seconds]);
  assert.equal(m.combo_event,0);assert.equal(m.judgment_event,0);assert.equal(m.row_note_count,chord?2:1);
 }
 assert.deepEqual(d,before);
 const[again,fresh]=recoverRows({...d,matches});assert.equal(again.length,matches.length);assert.deepEqual(fresh,[]);
});
for(const mode of['no_word','miss','non_synchronized','competing_note','competing_event','already_owned','hold','unknown','failed_clock','same_lane','stagger','too_precise','hold_risk','processing_conflict','foreign_popup_owner'])
test(`bounded refresh cannot replace missing or contradictory proof: ${mode}`,()=>{
 const d=scene();
 if(mode==='foreign_popup_owner')d.judgment_events[0].anchor_combo_event=9;
 if(mode==='no_word')d.judgment_events=[];
 if(mode==='miss')d.judgment_events[0].label='MISS';
 if(mode==='non_synchronized')d.judgment_events[0].lower_seconds+=.1;
 if(mode==='competing_note')d.notes.push({...d.notes[0],target_seconds:d.notes[0].target_seconds+.015,lane:1});
 if(mode==='competing_event')d.judgment_events.push({...d.judgment_events[0],lower_seconds:1.045,upper_seconds:1.05});
 if(mode==='already_owned')d.matches.push({note:0,target_seconds:1,combo_event:0,observation_lower_seconds:1.044,observation_upper_seconds:1.061});
 if(mode==='hold')d.notes[0].note_type='hold';
 if(mode==='unknown')d.notes[0].type_status='unknown';
 if(mode==='failed_clock')d.notes[0].timing_reconstruction.status='failed';
 if(mode==='same_lane')d.notes.push({...d.notes[0]});
 if(mode==='stagger')d.notes.push({...d.notes[0],lane:1,target_seconds:d.notes[0].target_seconds+.001});
 if(mode==='too_precise')d.notes[0].prediction_uncertainty_seconds=.0001;
 if(mode==='hold_risk')d.hold_analysis.unresolved_tracks.push({visible_start_seconds:1,visible_end_seconds:1.2});
 if(mode==='processing_conflict')d.visual_channels={processing:{notes:[{note:0,status:'disappeared_near_receptor',range:[.5,.52]}]}};
 const[matches,recovered]=recoverRows(d);assert.deepEqual(recovered,[]);assert.equal(matches.length,d.matches.length);
});
test('an explicit display correction changes compatibility without changing popup bounds',()=>{
 const d=scene(40,60,false,.05),[matches]=recoverRows(d);assert.equal(matches.length,1);
 assert.equal(matches[0].observation_lower_seconds,1.094);assert.ok(matches[0].association_target_range[0]<=1);
 d.display_delay_correction_ms=0;assert.deepEqual(recoverRows(d)[1],[]);
});

for(const fps of[30,60,120])test(`stale captured frames keep their ambiguity after refresh recovery at ${fps} fps`,()=>{
 const d=scene(40,fps),native=nativeScene([[1.05,0]],40,fps,5,{end:1.4,repeated:[[.85,1.15]]});
 const state={...native.scroll_motion,spacing:40,height:native.analysis_height,strict_clock:true};
 const clock=crossing(state,state.samples[0],1.05*240,1);
 assert.equal(clock.fit_method,'shared_scroll_frame_bounds');assert.ok(clock.prediction_uncertainty_seconds>.1);
 d.notes=[{...native.notes[0],...clock,type_status:'tap',timing_reconstruction:{status:'restored'}}];
 d.scroll_motion=native.scroll_motion;const before=structuredClone(d);
 d.combo_events[0].lower_seconds=d.judgment_events[0].lower_seconds=1.08;
 d.combo_events[0].upper_seconds=d.judgment_events[0].upper_seconds=1.08+1/fps;
 const[matches]=recoverRows(d);assert.equal(matches.length,1);
 assert.ok(matches[0].source_target_range[0]<=1.05&&matches[0].source_target_range[1]>=1.05);
 assert.equal(d.notes[0].native_clock_warning.reason,'shared_subframe_clock_unresolved');
 assert.deepEqual(d.notes,before.notes);assert.deepEqual(d.scroll_motion,before.scroll_motion);
 d.notes[0].prediction_uncertainty_seconds=.5/fps;assert.deepEqual(recoverRows(d)[1],[],
  'replacing the acquired stale-frame bracket with a nominal half-frame error loses compatibility');
});

test('presentation retains bounded-refresh provenance separately from lane evidence',()=>{
 const d=scene();d.native_body_risk_available=true;
 d.visual_channels={note_types:{notes:[{note:0,observations:[{kind:'tap',role:'tap',playback_seconds:.5,
  source_pts_seconds:80.5,reason:'image_cap_with_native_clearance'}]}]}};
 const before=structuredClone(d),view=present(d);
 assert.equal(view.matches.length,1);assert.equal(view.matches[0].recovery_method,'exclusive_bounded_target_with_synchronized_refreshes');
 assert.deepEqual(view.recovered_bounded_target_notes,[0]);assert.deepEqual(view.recovered_lane_supported_notes,[]);
 assert.equal(view.notes[0].target_seconds,d.notes[0].target_seconds);
 assert.deepEqual(view.notes[0].points,d.notes[0].points);assert.deepEqual(d,before);
});

test('bounded popup anchors do not displace a row with an independent receptor onset',()=>{
 const d=scene(),native=nativeScene([[1,0],[1.2,1],[1.15,2]],40,60);
 d.notes.push(...native.notes.slice(1).map(n=>({...n,type_status:'tap',timing_reconstruction:{status:'restored'}})));
 d.combo_events.push({...d.combo_events[0],lower_seconds:1.2,upper_seconds:1.217});
 d.judgment_events.push({...d.judgment_events[0],lower_seconds:1.2,upper_seconds:1.217});
 d.visual_channels={receptors:{events:[{lane:1,lit:true,frames:3,onset_range:[1.2,1.217],
  onset_source_pts_seconds:[81.2,81.217],start_seconds:1.217,end_seconds:1.25}]}};
 const[matches]=recoverRows(d),onset=matches.find(m=>m.note===1);
 assert.ok(onset,'a later conditional clock association cannot change the independent row proposal');
 assert.equal(onset.recovery_method,'unique_row_with_independent_lane_onset');assert.equal(onset.combo_event,1);
 assert.ok(matches.some(m=>m.note===0&&m.recovery_method==='exclusive_bounded_target_with_synchronized_refreshes'));
 assert.ok(!matches.some(m=>m.note===2));
});

for(const chord of[false,true])test(`an exclusive synchronized row can resolve a point-compatible unassigned refresh: chord=${chord}`,()=>{
 const d=scene(40,60,chord);d.notes.forEach(n=>{n.target_seconds=1;});
 d.combo_events[0].lower_seconds=d.judgment_events[0].lower_seconds=1.01;
 d.combo_events[0].upper_seconds=d.judgment_events[0].upper_seconds=1.027;
 const[matches,recovered]=recoverRows(d);
 assert.deepEqual(recovered,chord?[0,1]:[0]);assert.equal(matches.length,chord?2:1);
 for(const m of matches){assert.equal(m.combo_event,0);assert.equal(m.judgment_event,0);assert.equal(m.target_seconds,1);}
});

for(const fps of[30,60,120])for(const spacing of[20,40,80])test(`a uniquely overlapping delayed counter retains its original bracket: ${fps} fps / spacing ${spacing}`,()=>{
 const d=scene(spacing,fps);d.notes[0].target_seconds=1;
 const frames=d.scroll_motion.samples.map(s=>s.time),at=frames.findIndex(t=>Math.abs(t-1)<1e-8),delay=Math.ceil(.03*fps)+1;
 Object.assign(d.judgment_events[0],{lower_seconds:frames[at],upper_seconds:frames[at+1]});
 Object.assign(d.combo_events[0],{lower_seconds:frames[at-1],upper_seconds:frames[at+delay]});
 const before=structuredClone(d),[matches]=recoverRows(d);assert.equal(matches.length,1);
 assert.equal(matches[0].combo_event,0);assert.equal(matches[0].judgment_event,0);
 assert.deepEqual([matches[0].combo_lower_seconds,matches[0].combo_upper_seconds],[frames[at-1],frames[at+delay]]);
 for(const e of[d.combo_events[0],d.judgment_events[0]])assert.ok(frames.includes(e.lower_seconds)&&frames.includes(e.upper_seconds));
 assert.deepEqual(d,before);
 d.judgment_events.push({...d.judgment_events[0],lower_seconds:frames[at+1],upper_seconds:frames[at+2]});
 assert.deepEqual(recoverRows(d)[1],[],'a second feasible native refresh prevents the exclusive recovery');
});

test('a counter-owned row receives a word grade through its uniquely overlapping native bracket',()=>{
 const d=scene(40,120);d.notes[0].target_seconds=1;
 const frames=d.scroll_motion.samples.map(s=>s.time),at=frames.findIndex(t=>Math.abs(t-1)<1e-8),lo=frames[at+1],hi=frames[at+12];
 Object.assign(d.combo_events[0],{status:'matched',reason:null,lower_seconds:lo,upper_seconds:hi});
 d.matches=[{note:0,target_seconds:1,combo_event:0,row_note_count:1,combo_lower_seconds:lo,combo_upper_seconds:hi}];
 d.unsupported_intervals=[];d.coverage={};const before=structuredClone(d);
 const r=mergeJudgments(d,[{label:'GOOD',lower_seconds:frames[at+7],upper_seconds:frames[at+8],detection_status:'candidate'}]);
 assert.equal(r.matches.length,1);assert.equal(r.matches[0].judgment_label,'GOOD');
 assert.equal(r.matches[0].judgment_label_source,'synchronized_refresh');assert.equal(r.matches[0].judgment_event,0);
 assert.deepEqual([r.matches[0].combo_lower_seconds,r.matches[0].combo_upper_seconds],[lo,hi]);
 assert.equal(r.matches[0].target_seconds,1);assert.deepEqual(d.notes,before.notes);assert.deepEqual(d.scroll_motion,before.scroll_motion);
});

test('a broad counter bracket cannot take a word from another independently supported row',()=>{
 const d=scene(),native=nativeScene([[1.09,0],[1,1]],40,60,5,{end:1.4});
 d.notes=native.notes.map(n=>({...n,type_status:'tap',timing_reconstruction:{status:'restored'}}));
 d.scroll_motion=native.scroll_motion;
 const frames=native.scroll_motion.samples.map(s=>s.time),at=frames.findIndex(t=>Math.abs(t-1)<1e-8),lo=frames[at+2],hi=frames[at+3];
 Object.assign(d.combo_events[0],{status:'matched',reason:null,lower_seconds:frames[at+1],upper_seconds:frames[at+6]});
 d.matches=[{note:0,target_seconds:1.09,combo_event:0,row_note_count:1,combo_lower_seconds:frames[at+1],combo_upper_seconds:frames[at+6]}];
 d.unsupported_intervals=[];d.coverage={};
 d.visual_channels={receptors:{events:[{lane:1,lit:true,frames:4,onset_range:[lo,hi],
  onset_source_pts_seconds:[80+lo,80+hi],start_seconds:hi,end_seconds:hi+.05}]}};
 const labeled=mergeJudgments(d,[{label:'PERFECT',lower_seconds:lo,upper_seconds:hi,detection_status:'candidate'}]);
 assert.equal(labeled.matches.find(m=>m.note===0).judgment_label,undefined,'bracket overlap does not establish note-row identity');
 const[matches]=recoverRows(labeled),owned=matches.find(m=>m.note===1);
 assert.ok(owned);assert.equal(owned.judgment_event,0);assert.equal(owned.recovery_method,'unique_row_with_independent_lane_onset');
 assert.equal(matches.find(m=>m.note===0).combo_event,0);
});
