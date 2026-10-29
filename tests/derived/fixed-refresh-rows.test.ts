import test from 'node:test';
import assert from 'node:assert/strict';
import type {RecordData} from '../../src/piu_timeline/derived/types.ts';
import {mkdtempSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {prepare,type PresentationInput} from '../../src/piu_timeline/derived/pipeline/presentation.ts';
import {contracts} from '../../src/piu_timeline/derived/contracts.ts';
import {nativeScene} from './fixtures.ts';
import {recoverRows} from '../../src/piu_timeline/derived/recovery.ts';

function scene(spacing=40,fps=60,earlier=false):RecordData{
 const fixed=earlier?.9:1.1,d=nativeScene([[1,0],[fixed,1]],spacing,fps,5,{end:1.4});
 d.notes.forEach(n=>Object.assign(n,{type_status:'tap',timing_reconstruction:{status:'restored'},prediction_uncertainty_seconds:.04}));
 const scale=spacing/40,error=contracts.native_anchor.coordinate_uncertainty_pixels*scale;
 d.head_registration={format:{native_cap_registration:structuredClone(contracts.native_anchor)},notes:d.notes.map((n,i)=>({
  note:i,coordinate_method:'native_image_anchors',observations:n.points.map(([time,y])=>({time,source_pts_seconds:80+time,
   native_y_pixels:y,template:`generated-cap-${i}`,native_cap_coordinate_uncertainty_pixels:error,native_cap_reference_scale_y:scale}))}))};
 const times=d.scroll_motion.samples.map(s=>s.time),at=t=>times.find(v=>v>=t-1e-9);
 const lo=at(1),hi=times[times.indexOf(lo)+1],a=at(fixed),b=times[times.indexOf(a)+1];
 return {...d,median_frame_interval_seconds:1/fps,
  matches:[{note:1,target_seconds:fixed,combo_event:1,judgment_event:1,row_note_count:1,
   combo_lower_seconds:a,combo_upper_seconds:b,judgment_label:'PERFECT'}],
  combo_events:[{delta:1,status:'excluded',reason:'ambiguous_note_or_combo_association',lower_seconds:lo,upper_seconds:hi},
   {delta:1,status:'matched',lower_seconds:a,upper_seconds:b}],
  judgment_events:[{label:'PERFECT',detection_status:'candidate',lower_seconds:lo,upper_seconds:hi},
   {label:'PERFECT',detection_status:'candidate',anchor_combo_event:1,lower_seconds:a,upper_seconds:b}],
  hold_analysis:{holds:[],unresolved_tracks:[],receptor_runs:[{lane:1,lit:true,frames:3,onset_range:[a,b],
   onset_source_pts_seconds:[80+a,80+b],start_seconds:b,end_seconds:b+1/fps}]} };
}
for(const spacing of[20,40,80])for(const fps of[30,60,120])for(const earlier of[false,true])
test(`fixed corroborated row does not compete twice: ${spacing} spacing / ${fps} fps / earlier=${earlier}`,()=>{
 const d=scene(spacing,fps,earlier);
 // Ensure both individual timing windows include the incoming popup.
 const e=d.combo_events[0];d.notes[1].prediction_uncertainty_seconds=Math.abs(d.notes[1].target_seconds-(e.lower_seconds+e.upper_seconds)/2)-.045+.005;
 const before=structuredClone(d),[matches,recovered]=recoverRows(d);
 assert.deepEqual(recovered,[0]);assert.equal(matches.length,2);assert.deepEqual(matches.find(m=>m.note===1),before.matches[0]);
 const m=matches.find(m=>m.note===0);assert.equal(m.combo_event,0);assert.equal(m.judgment_event,0);
 assert.equal(m.target_seconds,1);assert.deepEqual(m.source_target_range,[.96,1.04]);
 assert.deepEqual([m.observation_lower_seconds,m.observation_upper_seconds],[e.lower_seconds,e.upper_seconds]);
 assert.equal(m.fixed_refresh_rows.length,1);const p=m.fixed_refresh_rows[0];assert.equal(p.note,1);
 assert.equal(p.physical_evidence.kind,'exclusive_lane_onset');
 assert.ok(p.native_row_separation[0].samples.length>=4);
 assert.ok(p.native_row_separation[0].samples.every(s=>s.ordered_gap_pixels>p.native_row_separation[0].position_error_pixels));
 assert.deepEqual(d,before);assert.deepEqual(recoverRows({...d,matches})[1],[]);
});
for(const mode of['no_physical','no_word','wrong_word','miss','shared_onset','same_row','wrong_observed_order','missing_pts','failed_block','unknown_type','hold_risk'])
test(`an assigned competitor needs independent proof: ${mode}`,()=>{
 const d=scene();d.notes[1].prediction_uncertainty_seconds=.07;
 if(mode==='no_physical')d.hold_analysis.receptor_runs=[];
 if(mode==='no_word')delete d.matches[0].judgment_event;
 if(mode==='wrong_word')d.judgment_events[1].anchor_combo_event=0;
 if(mode==='miss')d.judgment_events[1].label='MISS';
 if(mode==='shared_onset'){
  d.notes.push({...d.notes[1]});d.matches.push({...d.matches[0],note:2});
 }
 if(mode==='same_row')d.notes[1].target_seconds=d.matches[0].target_seconds=1;
 if(mode==='wrong_observed_order')d.notes[1].points=d.notes[1].points.map(([t,y])=>[t,y-80]);
 if(mode==='missing_pts')d.scroll_motion.samples.forEach(s=>{delete s.source_pts;});
 if(mode==='failed_block')d.scroll_motion.coordinate_registration.chunks[0].status='failed';
 if(mode==='unknown_type')d.notes[1].type_status='unknown';
 if(mode==='hold_risk')d.hold_analysis.unresolved_tracks.push({visible_start_seconds:.9,visible_end_seconds:1.2});
 const before=structuredClone(d),[matches,recovered]=recoverRows(d);
 assert.deepEqual(recovered,[]);assert.equal(matches.length,d.matches.length);assert.deepEqual(d,before);
});

test('an independently observed disappearance can corroborate the fixed row',()=>{
 const d=scene();d.notes[1].prediction_uncertainty_seconds=.07;d.hold_analysis.receptor_runs=[];
 const e=d.combo_events[1],range=[e.lower_seconds,e.upper_seconds];
 d.visual_channels={processing:{notes:[{note:1,status:'disappeared_near_receptor',range,source_pts_seconds:range.map(t=>80+t)}]}};
 const before=structuredClone(d),[matches,recovered]=recoverRows(d);
 assert.deepEqual(recovered,[0]);assert.equal(matches.find(m=>m.note===0).fixed_refresh_rows[0].physical_evidence.kind,'note_disappearance');
 assert.deepEqual(d,before);
 d.visual_channels.processing.notes[0].source_pts_seconds[1]+=.001;
 assert.deepEqual(recoverRows(d)[1],[],'a processing bracket from a different source frame is not proof');
});
for(const mode of['onset_pts','duplicate_pts','overlapping_displays','opposite_target_order','too_few_positions','stale_match_target','aggregate_owner'])
test(`fixed row proof retains source and order requirements: ${mode}`,()=>{
 const d=scene();d.notes[1].prediction_uncertainty_seconds=.07;
 if(mode==='onset_pts')d.hold_analysis.receptor_runs[0].onset_source_pts_seconds[0]+=.001;
 if(mode==='duplicate_pts')d.scroll_motion.samples.forEach(s=>{s.source_pts=80;});
 if(mode==='overlapping_displays'){
  const e=d.combo_events[0];Object.assign(d.combo_events[1],{lower_seconds:e.lower_seconds,upper_seconds:e.upper_seconds});
  Object.assign(d.judgment_events[1],{lower_seconds:e.lower_seconds,upper_seconds:e.upper_seconds});
 }
 if(mode==='opposite_target_order')d.notes[1].target_seconds=d.matches[0].target_seconds=.9;
 if(mode==='too_few_positions')d.notes[1].points=d.notes[1].points.slice(0,3);
 if(mode==='stale_match_target')d.matches[0].target_seconds+=.05;
 if(mode==='aggregate_owner')d.matches[0].aggregate_row_count=2;
 assert.deepEqual(recoverRows(d)[1],[]);
});


test('the cached report pipeline carries the native proof and invalidates only consumed inputs',()=>{
 const d=scene();d.notes[1].prediction_uncertainty_seconds=.07;
 const frames=d.scroll_motion.samples.map(s=>({playback_seconds:s.time,source_pts_seconds:s.source_pts,notes:[],combo:null,combo_confidence:0}));
 const request:PresentationInput={schema:1,data:d,observations:{frames,visibility_frames:structuredClone(frames),occluders:[],
  native_body_risk_available:true,pre_hold_proofs:{}}};
 const directory=mkdtempSync(join(tmpdir(),'piu-fixed-rows-'));
 const stage=()=>JSON.parse(readFileSync(join(directory,'derived-stages/manifest.json'),'utf8')).stages.find(s=>s.stage==='hold-view');
 try{
  const before=structuredClone(request),view=prepare(request,directory);
  assert.equal(view.matches.length,2,'consumer projection must retain the fixed-row observation proof');
  assert.equal(view.matches.find(m=>m.note===0).fixed_refresh_rows[0].note,1);
  assert.deepEqual(request,before);assert.equal(stage().reused,false);
  prepare(request,directory);assert.equal(stage().reused,true);
  d.scroll_motion.samples[0].phase+=7;
  prepare(request,directory);assert.equal(stage().reused,true,'unused displacement phase is not a row-identity input');
  const frame=d.scroll_motion.samples.find(s=>s.time===d.hold_analysis.receptor_runs[0].onset_range[0]);
  frame.source_pts+=.001;
  const changed=prepare(request,directory);
  assert.equal(stage().reused,false,'the actual source-frame identity must invalidate the proof');
  assert.ok(!changed.matches.some(m=>m.note===0));
  assert.ok(changed.recognition_diagnostics.warnings.some(w=>w.note===0&&w.reason==='timing_evidence_unresolved'));
 }finally{rmSync(directory,{recursive:true,force:true});}
});

for(const mode of['missing_registration','wrong_reference_error','conflicting_reference','unmeasured_position','inconsistent_joint_gap'])
test(`a fixed row requires qualified image coordinate bounds: ${mode}`,()=>{
 const d=scene();d.notes[1].prediction_uncertainty_seconds=.07;
 if(mode==='missing_registration')delete d.head_registration;
 if(mode==='wrong_reference_error')d.head_registration.notes[0].observations.forEach(o=>{o.native_cap_coordinate_uncertainty_pixels=.01;});
 if(mode==='conflicting_reference')d.head_registration.notes[0].observations.forEach(o=>{o.native_cap_registration_status='conflicting';});
 if(mode==='unmeasured_position')d.head_registration.notes[0].observations.forEach(o=>{o.native_y_pixels+=.01;});
 if(mode==='inconsistent_joint_gap'){
  d.notes[1].points=d.notes[1].points.map(([t,y],i)=>[t,y+(i%2?3:-3)]);
  d.head_registration.notes[1].observations.forEach((o,i)=>{o.native_y_pixels=d.notes[1].points[i][1];});
 }
 assert.deepEqual(recoverRows(d)[1],[]);
});
