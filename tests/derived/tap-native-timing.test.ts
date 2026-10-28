import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeScene,template} from './fixtures.ts';
import {present} from '../../src/piu_timeline/derived/hold_presentation.ts';
import {draft} from '../../src/piu_timeline/derived/charts/draft.ts';
import {recognition} from '../../src/piu_timeline/derived/diagnostics.ts';

function scene(spacing=40,nextTarget=1.5){
 const d=nativeScene([[1,0],[nextTarget,1]],spacing);
 Object.assign(d,{chart:'S20',matches:[],combo_events:[],judgment_events:[{label:'PERFECT',delta:1,
  lower_seconds:.99,upper_seconds:1,status:'candidate',detection_status:'candidate'}],
  hold_analysis:{holds:[],unresolved_tracks:[],receptor_runs:[]},
  beat_timing:{warnings:[{note:0,lane:0,reason:'beat_timing_reconstruction_failed',visible_start_seconds:.99,visible_end_seconds:1.01}]},
  visual_channels:{note_types:{notes:d.notes.map((n,i)=>({note:i,observations:[{kind:'tap',role:'tap',
   playback_seconds:.5,source_pts_seconds:80.5,reason:'image_cap_with_native_clearance'}]}))},
   receptors:{events:[{lane:0,lit:true,frames:3,onset_range:[.99,1],onset_source_pts_seconds:[80.99,81],start_seconds:1,end_seconds:1.04}]}}});
 Object.assign(d.notes[0],{status:'excluded',reason:'beat_timing_reconstruction_failed',target_seconds:null,
  video_target_range:[.99,1.01],timing_reconstruction:{status:'restored'},beat_reconstruction:{status:'failed'}});
 return d;
}
for(const spacing of [20,40,80])test(`native tap timing survives failed beat placement at spacing ${spacing}`,()=>{
 const d=scene(spacing),before=structuredClone(d),view=present(d);
 assert.equal(view.notes[0].status,'estimated');assert.equal(view.notes[0].target_seconds,1);
 assert.equal(view.notes[0].target_timing_basis,'native_motion');assert.equal(view.notes[0].chart_timing_status,'unresolved');
 assert.equal(view.notes[0].beat_reconstruction.status,'failed');assert.deepEqual(view.notes[0].points,d.notes[0].points);
 const match=view.matches.find(m=>m.note===0);assert.ok(match,'independent receptor and word evidence can use native timing');
 assert.deepEqual([match.observation_lower_seconds,match.observation_upper_seconds],[.99,1]);
 assert.equal(match.judgment_label,'PERFECT');
 assert.ok(recognition(view,{notes:{}}).warnings.some(w=>w.note===0&&w.reason==='beat_timing_reconstruction_failed'));
 const [,evidence]=draft(template(),view,{song_start_seconds:0,uncertainty_seconds:0});
 assert.ok(!evidence.placements.some(p=>p.note===0));assert.ok(evidence.placements.some(p=>p.note===1));
 assert.ok(evidence.unresolved.some(p=>p.note===0));assert.deepEqual(d,before);
});
test('unknown, hold or conflicting roles and failed native clocks cannot become native taps',()=>{
 for(const mode of ['unknown','hold','conflict','native-failed','decorative']){
  const d=scene(),o=d.visual_channels.note_types.notes[0].observations;
  if(mode==='unknown')o[0].kind='unknown';
  if(mode==='hold')o[0].kind='hold';
  if(mode==='conflict')o.push({...o[0],kind:'hold'});
  if(mode==='native-failed')d.notes[0].timing_reconstruction.status='failed';
  if(mode==='decorative')d.notes[0].reason='decorative_art';
  assert.equal(present(d).notes[0].status,'excluded',mode);
 }
});
test('a previously omitted native tap remains a competing row instead of permitting a false exclusive match',()=>{
 const d=scene(40,1.08);
 Object.assign(d.judgment_events[0],{lower_seconds:1.035,upper_seconds:1.045});
 Object.assign(d.visual_channels.receptors.events[0],{lane:1,onset_range:[1.035,1.045],start_seconds:1.045,end_seconds:1.08});
 const omitted=structuredClone(d);omitted.visual_channels.note_types.notes[0].observations[0].kind='unknown';
 assert.ok(present(omitted).matches.some(m=>m.note===1));
 assert.ok(!present(d).matches.some(m=>m.note===1),'both plausible rows must participate in exclusivity checks');
});
