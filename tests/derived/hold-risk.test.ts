import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeScene} from './fixtures.ts';
import {capGuard} from '../../src/piu_timeline/derived/holds/risk.ts';

function scene(spacing=40){
  const data=nativeScene([[1,0],[1.25,0]],spacing,60,5);
  const hold={head_note:0,tail_note:1,start_range:[.98,1.02],end_range:[1.23,1.27],start_censored:false,end_censored:false,
    body_frames:8,body_evidence:'skin_start_body_end_images',geometry_native_endpoint_notes:[0,1]};
  for(const [i,range]of [[0,hold.start_range],[1,hold.end_range]]as const)Object.assign(data.notes[i],{
    status:'excluded',reason:'beat_timing_reconstruction_failed',target_seconds:null,video_target_range:range,
    timing_reconstruction:{status:'restored'},beat_reconstruction:{status:'failed'}});
  return {hold,notes:data.notes,spacing,cadence:1/60,extent_spacing:1};
}
for(const spacing of [20,40,80])test(`native endpoint guards do not require successful beat rows at spacing ${spacing}`,()=>{
  const input=scene(spacing),before=structuredClone(input);
  assert.ok(Math.abs(capGuard(input)-1/6)<1e-9);assert.deepEqual(input,before);
  assert.ok(Math.abs(capGuard({...input,extent_spacing:2})-1/3)<1e-9);
  input.notes[1].motion_clock.velocity=spacing*3;
  assert.ok(Math.abs(capGuard(input)-1/3)<1e-9,'use the slower independent endpoint measurement');
});
test('native failure, unmatched bounds or incomplete ownership never supply a future-hold guard',()=>{
  for(const mode of ['native-failure','missing-range','wrong-range','wrong-owner','decorative','censored','few-images','missing-speed']){
    const input=scene(),head=input.notes[0];
    if(mode==='native-failure')head.timing_reconstruction.status='failed';
    if(mode==='missing-range')delete head.video_target_range;
    if(mode==='wrong-range')head.video_target_range=[.97,1.02];
    if(mode==='wrong-owner')input.hold.geometry_native_endpoint_notes=[1];
    if(mode==='decorative')head.reason='decorative_art';
    if(mode==='censored')input.hold.start_censored=true;
    if(mode==='few-images')input.hold.body_frames=3;
    if(mode==='missing-speed'){delete head.velocity_pixels_per_second;delete head.motion_clock}
    assert.equal(capGuard(input),null,mode);
  }
});
test('ordinary fitted endpoints retain the two-frame guard floor',()=>{
  const input=scene();for(const n of input.notes){n.status='estimated';n.beat_reconstruction.status='restored'}
  input.cadence=.1;assert.equal(capGuard(input),.2);
});
