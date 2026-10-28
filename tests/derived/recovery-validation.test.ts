import test from 'node:test';
import assert from 'node:assert/strict';
import {coordinateRecoveryScene} from './fixtures.ts';
import {recover,validateRecovery} from '../../src/piu_timeline/derived/beats/recovery.ts';
import {prepare} from '../../src/piu_timeline/derived/beats/coordinates.ts';
import {validate} from '../../src/piu_timeline/derived/beats/validation.ts';
import {inputNotes,nativeRange} from '../../src/piu_timeline/derived/holds/input.ts';
import {chartProjection} from '../../src/piu_timeline/derived/hold_projection.ts';

for(const spacing of [20,40,80])for(const fps of [30,60,120])for(const source of ['none','affine','frame_bounds','coordinate_derived'])
test(`a rejected coordinate proposal cannot supply timing: spacing=${spacing}, fps=${fps}, source=${source}`,()=>{
  const {data,groups}=coordinateRecoveryScene(spacing,1.0625,false,source!=='none',fps),head=data.notes[7];
  if(source==='frame_bounds')Object.assign(head,{fit_method:'shared_scroll_frame_bounds',motion_clock:null,
    timing_reconstruction:{status:'restored',method:'shared_scroll_frame_bounds'}});
  if(source==='coordinate_derived')Object.assign(head,{fit_method:'native_beat_coordinate_interpolation',
    timing_reconstruction:{status:'restored',method:'native_coordinate_interval'}});
  const points=structuredClone(data.notes.map(n=>n.points)),registration=structuredClone(data.head_registration);
  const proofs=recover(data.notes,prepare(data,spacing,true),[[0,3,120]],0,0,0,groups,[0,0],spacing,data.scroll_motion);
  assert.equal(proofs[7].status,'restored');
  // Model a wrong proposed row, then let the real independent pair check reject
  // it using the generated native positions. The producer's clock is untouched.
  head.target_seconds=1.125;head.video_target_range=[1.12,1.13];
  Object.assign(proofs[7],{target_seconds:1.125,native_target_range:[1.12,1.13]});
  const [pairWarnings]=validate(data,data.notes,spacing,prepare(data,spacing,true));
  assert.ok(pairWarnings.some(w=>w.note===7));assert.equal(head.status,'excluded');
  const warnings=validateRecovery(data.notes,proofs);
  assert.ok(warnings.some(w=>w.note===7&&w.reason==='native_coordinate_failed_pair_validation'&&w.failure_detail==='beat_grid_conflicts_with_spatial_spacing'));
  assert.equal(proofs[7].status,'failed');assert.equal(head.beat_reconstruction.status,'failed');
  if(source==='none'||source==='coordinate_derived'){
    assert.equal(proofs[7].source_timing.independent,false);
    assert.equal(head.timing_reconstruction.status,'failed');assert.equal(nativeRange(head),null);
    assert.equal(proofs[7].native_interval_status,'failed');assert.equal(inputNotes(data.notes)[7].status,'excluded');
  }else{
    assert.equal(proofs[7].source_timing.independent,true);
    assert.deepEqual(head.video_target_range,[1.0525,1.0725]);
    assert.equal(head.fit_method,source==='affine'?'shared_scroll_clock':'shared_scroll_frame_bounds');
    assert.equal(proofs[7].native_interval_status,'original_clock_retained');
    const native=inputNotes(data.notes)[7];assert.equal(native.status,'estimated');assert.equal(native.target_seconds,1.0625);
    data.visual_channels={note_types:{notes:[{note:7,observations:[{kind:'tap'}]}]}};
    const view=chartProjection(data).notes[7];assert.equal(view.target_seconds,1.0625);assert.equal(view.target_timing_basis,'native_motion');
    data.visual_channels.note_types.notes[0].observations.push({kind:'hold'});
    assert.equal(chartProjection(data).notes[7].status,'excluded','conflicting type observations cannot activate a tap');
  }
  assert.deepEqual(data.notes.map(n=>n.points),points);assert.deepEqual(data.head_registration,registration);
  assert.deepEqual(validateRecovery(data.notes,proofs),[],'revalidation is idempotent');
});
