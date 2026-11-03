import test from 'node:test';
import assert from 'node:assert/strict';
import {fit,covering}from '../../../src/piu_timeline/derived/coordinates/phase_clock.ts';
import {parameters,same}from '../../../src/piu_timeline/derived/coordinates/clock_model.ts';
import {spacingFailures}from '../../../src/piu_timeline/derived/beats/spacing.ts';
import {prepare as gapDomains}from '../../../src/piu_timeline/derived/beats/gaps.ts';
import {measuredGapScene,nativeScene}from '../fixtures.ts';

test('one affine model remains identical across different note crossing diagnostics',()=>{
 const model={origin:.2,velocity:240,intercept:48,residual:3,window:[.2,1.3]},
  a={...model,selection:'precision',trimmed_outer_frames:5,bracket_phase_errors_pixels:[1,2],bracket_tolerance_pixels:4},
  b={...model,selection:'precision',trimmed_outer_frames:8,bracket_phase_errors_pixels:[2,1],bracket_tolerance_pixels:5},before=structuredClone({a,b});
 assert.ok(same(a,b));assert.ok(same(a,Object.fromEntries(Object.entries(b).reverse())));assert.deepEqual(parameters(a),model);assert.deepEqual({a,b},before);
 for(const field of ['origin','velocity','intercept','residual'])assert.equal(same(a,{...b,[field]:b[field]+1}),false);
 assert.equal(same(a,{...b,window:[.2,1.4]}),false);
 assert.equal(same({...a,acceleration:1},{...b,acceleration:2}),false);
});

for(const spacing of [20,40,80])for(const fps of [30,60,120])
test(`a complete registered phase bounds velocity despite capture delay and catch-up: spacing=${spacing}, fps=${fps}`,()=>{
 const d=nativeScene([[1,0],[1.1,1]],spacing,fps,5,{end:1.3,renderTime:t=>t-.012*Math.sin(2*Math.PI*(t-.2)/.4)}),
  before=structuredClone(d),models=fit(d.scroll_motion,spacing/40);
 assert.equal(models.length,1);const m=models[0],[lo,hi]=m.velocity_range_pixels_per_second;
 assert.ok(lo<=6*spacing&&6*spacing<=hi);assert.ok(hi-lo<spacing*1.5);
 for(const [v,b]of m.vertices)for(const sample of d.scroll_motion.samples)
  assert.ok(Math.abs(b+v*(sample.time-m.origin_seconds)-sample.phase)<=m.phase_error_pixels+1e-7);
 assert.deepEqual(d,before);
});
for(const invalid of ['reverse','pts','gap','missing_phase','nonlinear'])
test(`an invalid or nonuniform source phase cannot become a constant render clock: ${invalid}`,()=>{
 const d=nativeScene([[1,0],[1.1,1]],40,60,5,{end:1.3}),samples=d.scroll_motion.samples;
 if(invalid==='reverse')samples[20].phase=samples[19].phase-4;
 if(invalid==='pts')samples[20].source_pts=samples[19].source_pts;
 if(invalid==='gap')d.scroll_motion.samples=samples.filter(s=>s.time<.6||s.time>.7);
 if(invalid==='missing_phase')delete samples[20].phase;
 if(invalid==='nonlinear')for(const s of samples)s.phase=240*(s.time-Math.min(.2,Math.max(0,s.time-.4)));
 assert.deepEqual(fit(d.scroll_motion,1),[]);
});

function corrected(){
 const d=measuredGapScene(40,60,[[.85,0],[1.1,1]]);
 d.notes.forEach((n,i)=>{
  const original=n.target_seconds+(i?-.015:.015),velocity=i?264:216,phase=n.motion_target_phase;
  n.motion_clock={origin:0,velocity,intercept:phase-velocity*original,residual:3,window:i?[.95,1.25]:[.7,1.]};
  n.beat_reconstruction={status:'restored'};
 });
 return d;
}
test('musical gap validation uses the registered phase domain instead of two local point-clock corrections',()=>{
 const d=corrected(),before=structuredClone(d),checks=[];
 assert.ok(spacingFailures(d.notes,40,d.scroll_motion,null,checks).length,'source endpoints still need explicit registration proof');
 const support={lane_spacing_pixels:40,chunks:{},frames:{},observed:{},reference_notes:[],native_measurements:d.head_registration};
 const records=[];assert.deepEqual(spacingFailures(d.notes,40,d.scroll_motion,support,records),[]);
 assert.ok(records.some(r=>r.comparison_basis==='registered_render_phase_domain'));
 assert.deepEqual(d,before);
 d.notes[1].target_seconds+=.04;
 assert.ok(spacingFailures(d.notes,40,d.scroll_motion,support).some(w=>w.reason==='shared_spacing_reconstruction_conflict'));
});
test('one common source phase supplies row-difference constraints across different valid local clocks',()=>{
 const d=corrected();d.notes.forEach(n=>n.target_seconds=n.motion_clock.origin+((n.clock_target_phase??n.motion_target_phase)-n.motion_clock.intercept)/n.motion_clock.velocity);
 const proofs=gapDomains(d,[{notes:[0,1]}]);assert.equal(proofs.length,1);assert.ok(proofs[0].render_clock);
 assert.ok(proofs[0].target_gap_range_seconds[0]<=.25&&.25<=proofs[0].target_gap_range_seconds[1]);
 const model=fit(d.scroll_motion,1)[0];assert.ok(covering([model],[0,1],d.notes,proofs[0].native_gap_measurements.samples));
 assert.equal(covering([model],[0,99],d.notes,proofs[0].native_gap_measurements.samples),null);
});

for(const fps of [30,60,120])
test(`source timing covers delayed capture phase before musical reconstruction: ${fps}fps`,async()=>{
 const {MotionClock}=await import('../../../src/piu_timeline/derived/clocks.ts'),
  d=nativeScene([[.85,0],[.85,1],[1.1,2]],40,fps,5,{end:1.3,
   renderTime:t=>t-(1/fps)*(.5+.5*Math.sin(2*Math.PI*(t-.2)/.4))}),
  state={...d.scroll_motion,spacing:40,height:d.analysis_height},before=structuredClone(state),clock=new MotionClock(state);
 for(const [i,n]of d.notes.entries()){
  const result=clock.fit({note_index:i,lane:n.lane,points:n.points,coordinate_basis:'native_cap_center',
   registration_uncertainty_pixels:1,registration_offsets:{0:52+240*n.target_seconds}},52,d.layout);
  assert.ok(result);assert.ok(Math.abs(result.target_seconds-n.target_seconds)<=result.prediction_uncertainty_seconds);
  const proof=result.motion_clock_validation?.source_target_range_seconds;
  assert.ok(proof&&proof[0]<=n.target_seconds&&n.target_seconds<=proof[1]);
  assert.ok(!Object.hasOwn(result.motion_clock,'selection'));
 }
 assert.deepEqual(state,before);
});
