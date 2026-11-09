import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';
import {project}from '../../../src/piu_timeline/derived/holds/image_timing.ts';
import {attach}from '../../../src/piu_timeline/derived/hold_state.ts';
const notes=[{lane:0,status:'estimated',target_seconds:1,prediction_uncertainty_seconds:.01,velocity_pixels_per_second:100},
 {lane:0,status:'excluded',reason:'beat_timing_reconstruction_failed',target_seconds:99,
  prediction_uncertainty_seconds:.01,velocity_pixels_per_second:100,video_target_range:[1.2,1.22],
  timing_reconstruction:{status:'restored',proof:'large'},beat_reconstruction:{status:'failed',proof:'large'}},
 {lane:0,status:'estimated',target_seconds:1.26,prediction_uncertainty_seconds:.01,
  coordinate_measurements:[{unread:'large'}],tracking_connections:[{unread:'large'}]}];
const script=String.raw`
import json,sys
from piu_timeline.play.holds.state import timing_notes
print(json.dumps(timing_notes(json.load(sys.stdin))))
`;
test('sustained-state wire input discards acquisition proofs without changing recognition windows',()=>{
 const compact=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{input:JSON.stringify(notes),encoding:'utf8'}));
 assert.ok(!JSON.stringify(compact).includes('large'));
 assert.deepEqual(compact.map(n=>n.velocity_pixels_per_second),notes.map(n=>n.velocity_pixels_per_second));
 const frames=Array.from({length:20},(_,i)=>({playback_seconds:.95+i/60,source_pts_seconds:80.95+i/60,
  receptor_lit:[true],receptor_white_fraction:[1]})),
 holds=[{lane:0,start_range:[.99,1.01],end_range:[1.2,1.22],head_note:0,tail_note:1,covered_notes:[0,1],start_censored:false}],
 geometry={receptor:20,spacing:20,note_scale:1,edge_tolerance:.55};
 assert.deepEqual(attach({notes},frames,holds,geometry),attach({notes:compact},frames,holds,geometry));
 const images={image_connections:[{id:0,lane:0,head_note:0,tail_note:1,covered_notes:[0,1],body_frames:2,source_pts_range:[80,80.1]}]},
  source=notes.map((n,i)=>({...n,points:[[.9+i*.02,200+i*20]]})),
  reduced=compact.map((n,i)=>({...n,points:source[i].points})),
  originalHolds=project(source,images),compactHolds=project(reduced,images);
 assert.deepEqual(compactHolds.observed_holds,originalHolds.observed_holds);
 assert.deepEqual(compactHolds.holds.map(h=>[h.head_note,h.tail_note,h.start_range,h.end_range]),
  originalHolds.holds.map(h=>[h.head_note,h.tail_note,h.start_range,h.end_range]));
});
