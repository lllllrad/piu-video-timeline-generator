import test from 'node:test';
import assert from 'node:assert/strict';
import {fit} from '../../../src/piu_timeline/derived/clocks.ts';
import {nativeScene} from '../fixtures.ts';

function scene(spacing=40,fps=60,speed=2){
 const data=nativeScene([[3.2,0]],spacing,fps,5,{end:3.6,speedSpacingPerSecond:speed});
 const state={...data.scroll_motion,height:data.analysis_height,spacing,
  samples:data.scroll_motion.samples.map(s=>({...s,lanes:5,displacement_basis:'independent_registered_peers'}))};
 const track={...data.notes[0],note_index:0,coordinate_basis:'native_cap_center',registration_uncertainty_pixels:.025*spacing};
 return {state,track,layout:data.layout,receptor:data.layout.receptor_y*data.analysis_height,truth:3.2};
}
for(const spacing of[20,40,80])for(const fps of[30,60,120])for(const speed of[1.5,2,3])
test(`a captured slow approach uses peer travel through the receptor: spacing=${spacing}, fps=${fps}, speed=${speed}`,()=>{
 const s=scene(spacing,fps,speed),before=structuredClone(s),result=fit(s.state,s.track,s.receptor,s.layout);
 assert.equal(result?.status,'estimated');
 assert.ok(Math.abs(result.target_seconds-s.truth)<1e-8);
 const last=s.track.points.at(-1)[0];assert.ok(result.target_seconds-last>.25);
 const proof=result.motion_clock_validation.supported_approach;
 assert.equal(proof.method,'continuous_independent_peer_motion');
 assert.ok(proof.playback_range_seconds[0]<=last&&proof.playback_range_seconds[1]>=s.truth-1e-8);
 assert.equal(proof.source_pts_seconds[0],80+proof.playback_range_seconds[0]);
 assert.equal(proof.source_pts_seconds.at(-1),80+proof.playback_range_seconds[1]);
 assert.ok(proof.source_pts_seconds.every((p,i)=>!i||p>proof.source_pts_seconds[i-1]));
 assert.deepEqual(s,before);
});
for(const mode of['missing-pts','repeated-pts','pts-gap','capture-gap','unsupported','single-lane','unmeasured-motion'])
test(`a long approach cannot use an unobserved or unqualified continuation: ${mode}`,()=>{
 const s=scene(),last=s.track.points.at(-1)[0],index=s.state.samples.findIndex(p=>p.time>last+.08),sample=s.state.samples[index];
 if(mode==='missing-pts')delete sample.source_pts;
 if(mode==='repeated-pts')sample.source_pts=s.state.samples[index-1].source_pts;
 if(mode==='pts-gap')sample.source_pts+=1;
 if(mode==='capture-gap')s.state.samples.splice(index,4);
 if(mode==='unsupported')sample.support=0;
 if(mode==='single-lane')sample.lanes=1;
 if(mode==='unmeasured-motion')sample.displacement_basis='unsupported';
 assert.equal(fit(s.state,s.track,s.receptor,s.layout),null);
});
