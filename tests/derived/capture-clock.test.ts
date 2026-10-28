import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeScene} from './fixtures.ts';
import {crossing} from '../../src/piu_timeline/derived/clocks.ts';

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

test('a missing capture interval is not filled with repeated observations',()=>{
  const data=nativeScene([[1.01,0]],40,60,5,{end:1.4,repeated:[[1,1+4/60]],dropped:[48,49,50,51]});
  const state={...data.scroll_motion,spacing:40,height:data.analysis_height};
  const result=crossing(state,state.samples[0],1.01*240,.75);
  assert.ok(result);
  const times=new Set(state.samples.map(s=>s.time));
  assert.ok(result.crossing_frame_seconds.every(t=>times.has(t)),'every bracket endpoint is a retained native frame');
  assert.deepEqual(result.crossing_source_pts_seconds,result.crossing_frame_seconds.map(t=>80+t));
});
