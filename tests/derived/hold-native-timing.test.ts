import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeScene,template} from './fixtures.ts';
import {inputNotes} from '../../src/piu_timeline/derived/holds/input.ts';
import {chartProjection} from '../../src/piu_timeline/derived/hold_projection.ts';
import {draft} from '../../src/piu_timeline/derived/charts/draft.ts';
import {recognition} from '../../src/piu_timeline/derived/diagnostics.ts';

function fixture(){
  const data=nativeScene([[1,0],[1.25,0],[1.5,1]]);
  Object.assign(data,{chart:'S20',start_seconds:0,end_seconds:3});
  Object.assign(data.notes[0],{status:'excluded',reason:'beat_timing_reconstruction_failed',target_seconds:null,
    video_target_range:[.97,1.03],timing_reconstruction:{status:'restored'},beat_reconstruction:{status:'failed',reason:'ambiguous_beat_rows'}});
  data.notes[2].type_status='tap';
  data.beat_timing={warnings:[{note:0,lane:0,reason:'beat_timing_reconstruction_failed',visible_start_seconds:.97,visible_end_seconds:1.03}]};
  data.hold_analysis={holds:[{id:0,lane:0,head_note:0,tail_note:1,covered_notes:[0,1],start_range:[.97,1.03],end_range:[1.24,1.26],
    start_censored:false,end_censored:false,last_body_seconds:1.2,geometry_native_endpoint_notes:[0],chart_timing_status:'unresolved',input:{segments:[]}}]};
  return data;
}
test('native geometry preparation retains observed bounds while beat assignment still fails',()=>{
  const data=fixture(),before=structuredClone(data),notes=inputNotes(data.notes);
  assert.equal(notes[0].status,'estimated');assert.deepEqual(notes[0].geometry_native_range,[.97,1.03]);
  assert.equal(notes[0].beat_reconstruction.status,'failed');assert.deepEqual(notes[0].points,data.notes[0].points);assert.deepEqual(data,before);
  for(const changes of [{timing_reconstruction:{status:'failed'}},{video_target_range:undefined},{video_target_range:[1,1]},{video_target_range:[1,NaN]},{reason:'decorative_art'},{beat_reconstruction:{status:'restored'}}]){
    const original={...data.notes[0],...changes};assert.equal(inputNotes([original])[0].status,'excluded');
  }
});
test('a measured hold remains displayed, retains its warning and cannot supply a UCS placement',()=>{
  const data=fixture(),before=structuredClone(data),view=chartProjection(data);
  assert.equal(view.hold_analysis.holds.length,1);assert.equal(view.notes[0].note_type,'hold');assert.equal(view.notes[0].status,'estimated');
  assert.deepEqual(view.notes[0].beat_reconstruction,data.notes[0].beat_reconstruction);
  assert.equal(recognition(view,{notes:{}}).warnings.filter(w=>w.reason==='beat_timing_reconstruction_failed').length,1);
  const [,evidence]=draft(template(),view,{song_start_seconds:0,uncertainty_seconds:0});
  assert.ok(evidence.placements.some(p=>p.note===2));assert.ok(!evidence.placements.some(p=>p.note===0));
  assert.ok(evidence.unresolved.some(p=>p.note===0&&p.reason==='Hold beat timing remains unresolved'));
  assert.deepEqual(data,before);
});
test('an unrelated or mismatched hold range cannot bypass a failed timing reconstruction',()=>{
  for(const change of ['no-native-proof','wrong-range','native-fit-failed']){
    const data=fixture(),h=data.hold_analysis.holds[0];
    if(change==='no-native-proof')delete h.geometry_native_endpoint_notes;
    if(change==='wrong-range')h.start_range=[.9,1.1];
    if(change==='native-fit-failed')data.notes[0].timing_reconstruction.status='failed';
    assert.equal(chartProjection(data).hold_analysis.holds.length,0);
  }
});
