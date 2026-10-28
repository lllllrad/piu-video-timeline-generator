import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {nativeScene} from './fixtures.ts';
import {crossing} from '../../src/piu_timeline/derived/clocks.ts';
import {frameBounds} from '../../src/piu_timeline/derived/frame_bounds.ts';
import {processingPaths} from '../../src/piu_timeline/derived/scroll.ts';

for(const fps of [30,60,120])for(const spacing of [20,40,80])test(`repeated native frames retain the full crossing ambiguity: ${fps} fps / spacing ${spacing}`,()=>{
  const hiddenTarget=1+.5/fps;
  const data=nativeScene([[hiddenTarget,0],[1.2,1]],spacing,fps,5,{end:1.4,repeated:[[1,1+4/fps]]});
  const before=structuredClone(data),state={...data.scroll_motion,spacing,height:data.analysis_height};
  const result=crossing(state,state.samples[0],hiddenTarget*spacing*6,.75);
  assert.ok(result);assert.ok(result.target_seconds-result.prediction_uncertainty_seconds<=hiddenTarget&&hiddenTarget<=result.target_seconds+result.prediction_uncertainty_seconds,
    'a repeated old image cannot move the true crossing outside the reported range');
  assert.ok(result.crossing_frame_seconds[0]<=1-1/fps+1e-9);
  assert.ok(result.crossing_frame_seconds[1]>=1+5/fps-1e-9);
  assert.deepEqual(result.crossing_source_pts_seconds,result.crossing_frame_seconds.map(t=>80+t));
  assert.deepEqual(data,before);
});

for(const fps of [30,60,120])test(`ordinary capture retains its existing precision at ${fps} fps`,()=>{
  const data=nativeScene([[1.01,0],[1.2,1]],40,fps,5,{end:1.4});
  const state={...data.scroll_motion,spacing:40,height:data.analysis_height};
  const result=crossing(state,state.samples[0],1.01*240,.1);
  assert.ok(result);assert.equal(result.stationary_phase_interval,undefined);
  assert.ok(result.prediction_uncertainty_seconds<=.5/fps+1e-9);
  assert.ok(Math.abs(result.target_seconds-1.01)<1e-9);
});

test('a missing capture interval cannot be replaced by an unsupported interpolation',()=>{
  const data=nativeScene([[1.01,0]],40,60,5,{end:1.4,repeated:[[1,1+4/60]],dropped:[48,49,50,51]});
  const state={...data.scroll_motion,spacing:40,height:data.analysis_height};
  const result=crossing(state,state.samples[0],1.01*240,.75);
  assert.equal(result,null,'a gap over the native continuity limit cannot prove a bounded crossing');
});

for(const fps of [30,60,120])for(const spacing of [20,40,80])test(`unfitted stale capture retains every possible crossing: ${fps} fps / spacing ${spacing}`,()=>{
  const hiddenTarget=1.01,data=nativeScene([[hiddenTarget,0]],spacing,fps,5,{end:1.4,repeated:[[.85,1.15]]});
  const original=structuredClone(data),state={...data.scroll_motion,spacing,height:data.analysis_height,strict_clock:true};
  const result=crossing(state,state.samples[0],hiddenTarget*spacing*6,.025*spacing);
  assert.ok(result);assert.equal(result.fit_method,'shared_scroll_frame_bounds');assert.equal(result.motion_clock,null);
  assert.equal(result.native_clock_warning.reason,'shared_subframe_clock_unresolved');
  const lo=result.target_seconds-result.prediction_uncertainty_seconds,hi=result.target_seconds+result.prediction_uncertainty_seconds;
  assert.ok(lo<=hiddenTarget&&hiddenTarget<=hi);
  assert.ok(lo<=result.crossing_frame_seconds[0]&&hi>=result.crossing_frame_seconds[1]);
  assert.ok(result.prediction_uncertainty_seconds>.15,'the full repeated-image interval remains uncertain');
  assert.deepEqual(result.crossing_source_pts_seconds,result.crossing_frame_seconds.map(t=>80+t));
  assert.deepEqual(data,original);
});

for(const fps of [30,60,120])test(`phase jump is bounded by frames without assuming uniform speed: ${fps} fps`,()=>{
  const data=nativeScene([[1.01,0]],40,fps,5,{end:1.4,renderTime:t=>t<1?t:t+.12});
  const state={...data.scroll_motion,spacing:40,height:data.analysis_height,strict_clock:true};
  const result=crossing(state,state.samples[0],1.01*240,.75);
  assert.equal(result.fit_method,'shared_scroll_frame_bounds');
  assert.ok(result.crossing_frame_seconds[0]<1&&result.crossing_frame_seconds[1]>=1);
  assert.equal(result.motion_clock,null);assert.ok(result.native_clock_warning);
});

test('phase uncertainty expands the source bracket and fails when either boundary is unobserved',()=>{
  const data=nativeScene([[1.01,0]],40,60,5,{end:1.4}),samples=data.scroll_motion.samples,sample=samples[0];
  const precise=frameBounds(samples,sample,1.01*240,.75,1/60);
  const broad=frameBounds(samples,sample,1.01*240,12,1/60);
  assert.ok(broad.crossing_frame_seconds[0]<precise.crossing_frame_seconds[0]);
  assert.ok(broad.crossing_frame_seconds[1]>precise.crossing_frame_seconds[1]);
  assert.equal(frameBounds(samples,sample,1.01*240,500,1/60),null);
  const uncertain=structuredClone(samples);uncertain.forEach(s=>{if(s.time>.5)s.variance=144;});
  assert.deepEqual(frameBounds(uncertain,uncertain[0],1.01*240,0,1/60).crossing_frame_seconds,broad.crossing_frame_seconds);
});

test('registered restoration retains the imprecise-clock warning alongside bounded usable timing',()=>{
  const data=nativeScene(Array.from({length:16},(_,i)=>[.9+i*.04,i%5]),40,60,5,{end:1.8,
    renderTime:t=>t<.6?t:t<.9?.6+.2*(t-.6):t<1.2?.66+1.8*(t-.9):t});
  const script=`import json,sys
from copy import deepcopy
from piu_timeline.play.tracking import Track,fit_track
from piu_timeline.play.shared_timing import restore
s=json.load(sys.stdin);tracks=[Track(n['lane'],n['points'])for n in s['notes']]
before=deepcopy(tracks);timeline=deepcopy(s['scroll_motion']['samples'])
notes=[fit_track(t,52,40)for t in tracks]
for n in notes:n.update(native_clock_warning={'reason':'preliminary_only'},crossing_method='preliminary_only')
m,r=restore(notes,tracks,timeline,s['layout'],s['analysis_width'],s['analysis_height'])
assert tracks==before and timeline==s['scroll_motion']['samples']
print(json.dumps({'notes':notes,'result':r}))`;
  const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{
    cwd:fileURLToPath(new URL('../../',import.meta.url)),input:JSON.stringify(data),encoding:'utf8'}));
  const n=r.notes[10];assert.equal(n.status,'estimated');assert.equal(n.fit_method,'shared_scroll_frame_bounds');
  assert.ok(n.target_seconds-n.prediction_uncertainty_seconds<=1.3&&1.3<=n.target_seconds+n.prediction_uncertainty_seconds);
  const w=r.result.warnings.find(w=>w.note===10&&w.reason==='shared_subframe_clock_unresolved');assert.ok(w);
  assert.equal(r.result.status,'failed','usable bounds do not certify a recovered subframe clock');
  assert.deepEqual(w.crossing_source_pts_seconds,n.crossing_source_pts_seconds);
  assert.deepEqual([w.visible_start_seconds,w.visible_end_seconds],n.crossing_capture_range);
  const affine=r.notes.filter(n=>n.status==='estimated'&&n.motion_clock);assert.ok(affine.length);
  for(const note of affine){assert.equal(note.native_clock_warning,undefined);assert.equal(note.crossing_method,undefined);}
  const failed=r.notes.filter(n=>n.timing_reconstruction.status==='failed');assert.ok(failed.length);
  for(const note of failed){
    assert.equal(note.native_clock_warning,undefined);assert.equal(note.crossing_method,undefined);
    assert.equal(note.timing_reconstruction.unaccepted_previous_estimate.native_clock_warning.reason,'preliminary_only');
  }
});

for(const spacing of [20,40,80])test(`transferred coordinates without an affine clock retain their measured processing path: spacing ${spacing}`,()=>{
  const data=nativeScene([[1.01,0]],spacing,60,5,{end:1.4,renderTime:t=>t<1?t:t+.12});
  const n=data.notes[0],phase=n.motion_target_phase;
  Object.assign(n,{motion_clock:null,coordinate_bridge:{from_chunk:7,to_chunk:0},clock_target_phase:phase,
    timing_reconstruction:{status:'restored'},velocity_pixels_per_second:-spacing*6});
  const original=structuredClone(data);
  const path=processingPaths([n],data,spacing*1.3,spacing,1)[0];
  assert.equal(path.supported,true);assert.equal(path.basis,'registered_native_displacement');
  const samples=data.scroll_motion.samples,i=samples.findIndex((a,j)=>j<samples.length-1&&a.phase<=phase&&phase<samples[j+1].phase);
  assert.ok(i>=0);
  const measured=-(samples[i+1].phase-samples[i].phase)/(samples[i+1].time-samples[i].time);
  assert.equal(path.velocity,measured,'use the destination observation, not the old block average');
  assert.notEqual(path.velocity,n.velocity_pixels_per_second);
  assert.equal(path.position_model.phase,phase);assert.equal(path.position_model.chunk,0);
  assert.equal(n.motion_clock,null);assert.deepEqual(data,original);
});
