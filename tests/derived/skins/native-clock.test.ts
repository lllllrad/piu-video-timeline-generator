import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {nativeScene} from '../fixtures.ts';
import {fit} from '../../../src/piu_timeline/derived/native_clock.ts';
import type {RecordData} from '../../../src/piu_timeline/derived/types.ts';

function scene(spacing=40,fps=60,early=false,repeated=false){
 const data=nativeScene([[.93,0]],spacing,fps,5,{end:1.3}),stop=early?.79:.84;
 const track:RecordData={note_index:0,coordinate_basis:'native_cap_center',registration_uncertainty_pixels:spacing/40,
  points:data.scroll_motion.samples.map(s=>[s.time,data.layout.receptor_y*data.analysis_height+12*spacing*(.93-s.time)])
   .filter(([t,y])=>stop-.14-1e-8<=t&&t<=stop+1e-8&&y>(data.layout.receptor_y*data.analysis_height)+.85*spacing)};
 if(repeated)track.points.at(-1)[1]=track.points.at(-2)[1];
 const state={...data.scroll_motion,height:data.analysis_height,spacing},receptor=data.layout.receptor_y*data.analysis_height;
 return {data,track,state,receptor};
}
for(const spacing of [20,40,80])for(const fps of [30,60,120])for(const early of [false,true])
test(`a short certified approach requires its entire target domain inside the extrapolation budget: spacing=${spacing}, fps=${fps}, early=${early}`,()=>{
 const {data,track,state,receptor}=scene(spacing,fps,early),before=structuredClone({state,track});
 const r=fit(state,track,receptor,data.layout);
 // The earliest 30fps window no longer bounds every capture-phase model
 // within the declared 250ms extrapolation limit. It must fail as a whole.
 if(early&&fps===30){assert.equal(r,null);assert.deepEqual({state,track},before);return;}
 assert.ok(r);const [lo,hi]=r.native_interval_model.target_range_seconds;
 assert.ok(lo<=.93+1e-8&&.93<=hi+1e-8);assert.ok(hi<=track.points.at(-1)[0]+.25+1e-8);
 for(const [v,b]of r.native_interval_model.vertices)for(const o of r.native_interval_model.observations){
  const [a,z]=o.capture_range_seconds,t=r.native_interval_model.origin_seconds;
  assert.ok(b-v*(a-t)>=o.y_pixels-o.coordinate_uncertainty_pixels-1e-7);
  assert.ok(b-v*(z-t)<=o.y_pixels+o.coordinate_uncertainty_pixels+1e-7);
 }
 assert.equal(r.native_clock_warning.reason,'shared_subframe_clock_unresolved');
 assert.deepEqual({state,track},before);
 for(const o of r.native_interval_model.observations)assert.equal(o.source_pts_seconds,80+o.time);
});
test('a missing detector frame does not become a missing source frame',()=>{
 const {data,track,state,receptor}=scene();track.points.splice(4,1);
 const r=fit(state,track,receptor,data.layout);assert.ok(r);
 assert.ok(r.native_interval_model.target_range_seconds[0]<=.93&&r.native_interval_model.target_range_seconds[1]>=.93);
});
test('repeated image positions widen the feasible capture interval',()=>{
 const a=scene(),b=scene(40,60,false,true),plain=fit(a.state,a.track,a.receptor,a.data.layout),repeated=fit(b.state,b.track,b.receptor,b.data.layout);
 assert.ok(plain&&repeated);assert.ok(repeated.native_clock_warning.capture_plateau_seconds>0);
 assert.ok(repeated.prediction_uncertainty_seconds>plain.prediction_uncertainty_seconds);
 assert.ok(repeated.native_interval_model.target_range_seconds[0]<=.93&&repeated.native_interval_model.target_range_seconds[1]>=.93);
});
for(const kind of ['raw_origin','no_error','reverse','excessive_curve','clipped','gap','conflict','future_speed'])
test(`native interval recovery rejects unsupported evidence: ${kind}`,()=>{
 const {data,track,state,receptor}=scene();
 if(kind==='raw_origin')track.coordinate_basis='image_reference_anchor';
 if(kind==='no_error')track.registration_uncertainty_pixels=0;
 if(kind==='reverse')track.points=track.points.map(([t,y])=>[t,500-y]);
 if(kind==='excessive_curve')track.points[4][1]+=3*state.spacing;
 if(kind==='clipped')state.samples=state.samples.filter(s=>s.time<.9);
 if(kind==='gap')state.samples=state.samples.filter(s=>s.time<.9||s.time>1.02);
 if(kind==='conflict')state.coordinate_conflicts=[{note:0,reason:'native_frame_displacement_conflict'}];
 if(kind==='future_speed')for(const s of state.samples)if(s.time>=track.points.at(-1)[0])s.native_displacement_interval={range_pixels:[15,16]};
 assert.equal(fit(state,track,receptor,data.layout),null);
});
test('the native adapter preserves bounded recovery and its unresolved-clock warning',()=>{
 const script=String.raw`
import json
from piu_timeline.play.tracking import Track
from piu_timeline.play.shared_timing import restore
layout={'receptor_y':.1,'note_y_max':.95,'lanes':[{'x':.1+i*.1}for i in range(5)]}
times=[.2+i/60 for i in range(75)]
track=Track(0,[(t,40+240*(1-t))for t in times if .7<=t<=.84]);track.coordinate_basis='native_cap_center';track.registration_uncertainty_pixels=1.
notes=[{'lane':0,'status':'excluded','reason':'shared_timing_reconstruction_failed','points':track.points,'motion_chunk':999,'motion_target_phase':999}]
motion,result=restore(notes,[track],[{'time':t,'source_pts':80+t}for t in times],layout,400,400)
print(json.dumps({'note':notes[0],'diagnostics':result}))
`;
 const result=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.equal(result.note.status,'estimated');assert.equal(result.note.fit_method,'source_bound_native_interval');
 assert.equal(result.note.motion_chunk,undefined);assert.equal(result.note.motion_target_phase,undefined);
 assert.ok(result.diagnostics.warnings.some(w=>w.reason==='shared_subframe_clock_unresolved'));
 assert.equal(result.diagnostics.failed_notes,0);assert.equal(result.diagnostics.restored_notes,1);
 assert.equal(result.diagnostics.warning_notes,1);assert.equal(result.diagnostics.status,'failed');
});

test('processing consumes the native position domain without moving it to a beat target',async()=>{
 const {processingPaths}=await import('../../../src/piu_timeline/derived/scroll.ts');
 const {data,track,state,receptor}=scene(),r=fit(state,track,receptor,data.layout);
 const note={lane:0,points:track.points,...r,target_seconds:9,video_target_range:[8,10],timing_reconstruction:{status:'restored'}};
 const before=structuredClone(note),path=processingPaths([note],data,receptor,40,1)[0];
 assert.ok(path.supported);assert.equal(path.basis,'source_bound_native_interval');
 assert.deepEqual(path.position_model.vertices,r.native_interval_model.vertices);
 assert.ok(Math.abs(path.target-.93)<.05);assert.deepEqual(note,before);
 note.timing_reconstruction.status='failed';assert.equal(processingPaths([note],data,receptor,40,1)[0].supported,false);
});

test('a long detector gap retains earlier same-identity positions when the source cadence is complete',()=>{
 const {data,track,state,receptor}=scene();
 const before=structuredClone(track.points);track.points=track.points.filter(([t],i)=>i<3||i>=before.length-2);
 assert.ok(track.points[3][0]-track.points[2][0]>.05);
 const r=fit(state,track,receptor,data.layout);assert.ok(r);
 assert.equal(r.native_interval_model.observations.length,track.points.length);
 assert.ok(r.native_interval_model.target_range_seconds[0]<=.93&&r.native_interval_model.target_range_seconds[1]>=.93);
 const a=track.points[2][0],b=track.points[3][0];state.samples=state.samples.filter(s=>s.time<=a||s.time>=b);
 assert.equal(fit(state,track,receptor,data.layout),null);
});

for(const spacing of [20,40,80])for(const fps of [30,60,120])for(const phase of [-1,1])
test(`a one-frame capture phase cannot exclude the known latent crossing: spacing=${spacing}, fps=${fps}, phase=${phase}`,()=>{
 const d=nativeScene([[.93,0]],spacing,fps,5,{end:1.3,speedSpacingPerSecond:12,renderTime:t=>t+phase/fps}),
  track={note_index:0,coordinate_basis:'native_cap_center',registration_uncertainty_pixels:spacing/160,
   points:d.notes[0].points.filter(([t])=>t<=.84)},state={...d.scroll_motion,height:d.analysis_height,spacing},
  before=structuredClone({state,track}),result=fit(state,track,d.layout.receptor_y*d.analysis_height,d.layout);
 assert.ok(result);const [lo,hi]=result.native_interval_model.target_range_seconds;
 assert.ok(lo<=.93&&.93<=hi,`${lo}..${hi} must contain the generator's independent target`);
 assert.equal(result.native_clock_warning.reason,'shared_subframe_clock_unresolved');
 assert.ok(result.prediction_uncertainty_seconds<.08);
 assert.deepEqual({state,track},before);
 for(const o of result.native_interval_model.observations)assert.equal(o.source_pts_seconds,80+o.time);
});

test('a one-frame phase excursion alone cannot prove a nonlinear clock',()=>{
 const {data,track,state,receptor}=scene();track.points[4][1]+=15;
 const result=fit(state,track,receptor,data.layout);assert.ok(result);
 assert.equal(result.native_clock_warning.reason,'shared_subframe_clock_unresolved');
 const [lo,hi]=result.native_interval_model.target_range_seconds;assert.ok(lo<=.93&&.93<=hi);
});
