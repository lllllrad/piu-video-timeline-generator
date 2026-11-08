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


for(const spacing of[20,40,80])for(const fps of[30,60,120])
test(`a briefly visible distant cap uses source-supported travel after it is hidden: spacing=${spacing}, fps=${fps}`,()=>{
 const s=scene(spacing,fps);s.track.points=s.track.points.filter(([t])=>.8<=t&&t<=1.1);
 assert.ok(s.track.points.at(-1)[1]-s.receptor>2.5*spacing);
 const result=fit(s.state,s.track,s.receptor,s.layout);
 assert.equal(result?.status,'estimated');assert.ok(Math.abs(result.target_seconds-s.truth)<1e-8);
 assert.ok(result.motion_clock_validation.supported_approach.playback_range_seconds[0]<=1.1);
 assert.equal(result.motion_clock_validation.supported_approach.source_pts_seconds.at(-1),80+s.truth);
 const stop=s.state.samples.findIndex(p=>p.time>=2);s.state.samples[stop].support=0;
 assert.equal(fit(s.state,s.track,s.receptor,s.layout),null,'an unsupported interval cannot carry an early fragment to its target');
});

test('a hidden cap uses observed acceleration after disappearance instead of extrapolating its earlier speed',()=>{
 const s=scene(),turn=1.5;
 s.track.points=s.track.points.filter(([t])=>t<=1.1);
 s.state.samples.forEach(p=>{p.phase=80*(p.time<=turn?p.time:turn+2*(p.time-turn));});
 const truth=turn+(s.truth-turn)/2,result=fit(s.state,s.track,s.receptor,s.layout);
 assert.equal(result?.status,'estimated');assert.ok(Math.abs(result.target_seconds-truth)<1e-8);
 assert.ok(Math.abs(result.target_seconds-s.truth)>.8);
 assert.ok(result.motion_clock_validation.supported_approach.phase_range_pixels[1]>=result.motion_target_phase);
});

for(const count of[1,2])test(`source-certified distinct peer positions qualify a one-lane continuation: peers=${count}`,()=>{
 const s=scene(),last=s.track.points.at(-1)[0];
 s.state.samples.forEach(p=>{if(p.time>last){p.lanes=1;p.support=count;
  p.displacement_basis=count===1?'measured_cap_displacement':'independent_registered_peers';
  p.native_displacement_interval={range_pixels:[0,4],notes:count===1?[1]:[1,2]};}});
 const result=fit(s.state,s.track,s.receptor,s.layout);
 assert.equal(result?.status,'estimated');assert.ok(Math.abs(result.target_seconds-s.truth)<1e-8);
 assert.ok(result.motion_clock_validation.supported_approach.certified_peer_steps.length>0);
 assert.ok(result.motion_clock_validation.supported_approach.certified_peer_steps.every(p=>p.native_displacement_interval.notes.every(i=>i!==0)));
});
for(const mode of['target-only','missing-certificate','duplicate-identities','negative-identity','reversed-range','invalid-range','unmeasured-continuation'])
test(`a narrow-lane continuation requires a valid independent native interval: ${mode}`,()=>{
 const s=scene(),last=s.track.points.at(-1)[0];
 s.state.samples.forEach(p=>{if(p.time>last){p.lanes=1;p.support=1;p.displacement_basis='measured_cap_displacement';
  p.native_displacement_interval={range_pixels:[0,4],notes:[1]};
  if(mode==='target-only')p.native_displacement_interval.notes=[0];
  if(mode==='missing-certificate')delete p.native_displacement_interval;
  if(mode==='duplicate-identities'){p.support=2;p.displacement_basis='independent_registered_peers';p.native_displacement_interval.notes=[1,1];}
  if(mode==='negative-identity')p.native_displacement_interval.notes=[-1];
  if(mode==='reversed-range')p.native_displacement_interval.range_pixels=[4,0];
  if(mode==='invalid-range')p.native_displacement_interval.range_pixels=[0,NaN];
  if(mode==='unmeasured-continuation')p.displacement_basis='registered_identity_continuation';
 }});
 assert.equal(fit(s.state,s.track,s.receptor,s.layout),null);
});
