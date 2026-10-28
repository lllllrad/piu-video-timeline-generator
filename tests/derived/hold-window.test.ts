import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeScene} from './fixtures.ts';
import {recognitionWindow,attach} from '../../src/piu_timeline/derived/hold_state.ts';

function scene(){
  const data=nativeScene([[.3,0],[.8,0],[1.1,0],[1.15,0]],40,60,5,{end:1.4});
  Object.assign(data.notes[2],{status:'excluded',reason:'beat_timing_reconstruction_failed',target_seconds:null,
    video_target_range:[1.09,1.11],timing_reconstruction:{status:'restored'},beat_reconstruction:{status:'failed'}});
  const hold={id:0,lane:0,head_note:1,tail_note:2,covered_notes:[1,2],start_range:[.79,.81],end_range:[1.09,1.11],start_censored:false,end_censored:false};
  const geometry={receptor:26,spacing:20,note_scale:.5,edge_tolerance:.55};
  const frames=data.scroll_motion.samples.map(s=>({playback_seconds:s.time,source_pts_seconds:s.source_pts,bodies:[],
    receptor_lit:[s.time>=.9&&s.time<=1.05,false,false,false,false]}));
  return {data,hold,geometry,frames};
}
test('a beat-rejected tail cannot turn a supported sustained window into zero duration',()=>{
  const {data,hold,geometry,frames}=scene(),before=structuredClone({data,hold,frames});
  const window=recognitionWindow(data,hold,geometry);
  assert.equal(window[0],.79);assert.ok(Math.abs(window[1]-(1.15-.5/60))<1e-9);
  const result=attach(data,frames,[hold],geometry,true)[0];
  assert.ok(result.input.segments.length);assert.ok(result.input.segments[0].frames>=2);
  assert.equal(result.input.press_range,null);assert.equal(result.input.release_range,null);
  assert.deepEqual({data,hold,frames},before);
});
test('a following native tap still bounds the hold response when its beat row is rejected',()=>{
  const {data,hold,geometry}=scene();
  Object.assign(data.notes[3],{status:'excluded',reason:'beat_timing_reconstruction_failed',target_seconds:null,
    video_target_range:[1.13,1.17],timing_reconstruction:{status:'restored'},beat_reconstruction:{status:'failed'}});
  assert.ok(Math.abs(recognitionWindow(data,hold,geometry)[1]-1.13)<1e-9);
});
test('an unknown tail time is never compared as playback zero',()=>{
  const {data,hold,geometry}=scene();Object.assign(hold,{end_range:null,last_body_seconds:1.12});
  data.notes[2].video_target_range=undefined;
  const window=recognitionWindow(data,hold,geometry);
  assert.equal(window[0],.79);assert.ok(window[1]>.79);
});
test('no measured receptor support still means no recognized hold state',()=>{
  const {data,hold,geometry,frames}=scene();for(const frame of frames)frame.receptor_lit.fill(false);
  assert.deepEqual(attach(data,frames,[hold],geometry,true)[0].input.segments,[]);
});
