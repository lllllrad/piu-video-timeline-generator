import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {measuredGapScene,nativeScene,template} from './fixtures.ts';
import {text} from '../../src/piu_timeline/derived/charts/ucs.ts';
import {NativeGapMeasurements,resolve} from '../../src/piu_timeline/derived/native_gaps.ts';
import {spacingFailures} from '../../src/piu_timeline/derived/beats/spacing.ts';
import {prepare} from '../../src/piu_timeline/derived/beats/coordinates.ts';
import {reconstruct} from '../../src/piu_timeline/derived/beats/stage.ts';
import {derive} from '../../src/piu_timeline/derived/cli.ts';

function failedSource(spacing=40,fps=60){
  const data=measuredGapScene(spacing,fps),warnings=spacingFailures(data.notes,spacing,data.scroll_motion);
  assert.ok(warnings.length);
  for(const w of warnings){const n=data.notes[w.note];
    n.timing_reconstruction={status:'failed',reason:w.reason,unaccepted_previous_estimate:{target_seconds:n.target_seconds,
      prediction_uncertainty_seconds:n.prediction_uncertainty_seconds,fit_method:n.fit_method}};
    Object.assign(n,{status:'excluded',reason:w.reason,target_seconds:null});
  }
  data.timing_reconstruction={format:{schema:1},status:'failed',warnings,failed_notes:2,restored_notes:0};
  return data;
}

for(const spacing of [20,40,80])for(const fps of [30,60,120])test(`declared endpoint errors preserve source clocks: spacing=${spacing}, fps=${fps}`,()=>{
  const data=failedSource(spacing,fps),before=structuredClone(data),r=resolve(data);
  assert.deepEqual(r.timing_reconstruction.native_gap_validation.restored_notes,[0,1]);
  assert.deepEqual(r.timing_reconstruction.warnings,[]);
  for(const proof of r.timing_reconstruction.native_gap_validation.comparisons){
    const [lo,hi]=proof.allowed_gap_range_pixels;assert.ok(lo<=.25*spacing*6&&.25*spacing*6<=hi);
    assert.ok(proof.samples.every(s=>s.source_pts_seconds===80+s.time));
  }
  r.notes.forEach((n,i)=>{assert.equal(n.status,'estimated');assert.equal(n.target_seconds,[.85,1.1][i]);
    assert.ok(n.prediction_uncertainty_seconds>=before.notes[i].prediction_uncertainty_seconds);});
  assert.deepEqual(data,before);assert.deepEqual(resolve(data),r);assert.deepEqual(resolve({...data,...r}),{});
  assert.deepEqual(r.notes.map(n=>n.points),data.notes.map(n=>n.points));
  assert.deepEqual(spacingFailures(r.notes,spacing,data.scroll_motion,prepare({...data,...r},spacing)),[],
    'later gap checks must use the same acquired uncertainty evidence');
});

for(const corruption of ['missing_uncertainty','wrong_scale','conflicting','wrong_position','source_pts','outlier','reference_model','stale_clock','duplicate_measurement','duplicate_pts'])
test(`unsupported native gap explanations retain warnings: ${corruption}`,()=>{
  const d=failedSource(),sample=d.head_registration.notes[0].observations[2];
  if(corruption==='missing_uncertainty')delete sample.native_cap_coordinate_uncertainty_pixels;
  if(corruption==='wrong_scale')sample.native_cap_reference_scale_y=2;
  if(corruption==='conflicting')sample.native_cap_registration_status='conflicting';
  if(corruption==='wrong_position')sample.native_y_pixels+=2;
  if(corruption==='source_pts')sample.source_pts_seconds+=1;
  if(corruption==='duplicate_measurement')d.head_registration.notes[0].observations.push({...sample});
  if(corruption==='duplicate_pts'){
    const previous=d.head_registration.notes[0].observations[1].source_pts_seconds;
    d.scroll_motion.samples.find(s=>s.time===sample.time).source_pts=previous;
    for(const r of d.head_registration.notes){const o=r.observations.find(o=>o.time===sample.time);if(o)o.source_pts_seconds=previous;}
  }
  if(corruption==='outlier'){
    d.notes[0].points[2][1]+=8;sample.native_y_pixels+=8;
  }
  if(corruption==='reference_model')d.timing_reconstruction.warnings.forEach(w=>{w.independent_coordinate_models=[{source:'separate_absolute_constraint'}];});
  if(corruption==='stale_clock')d.notes.forEach(n=>{n.motion_clock.intercept+=10;});
  const r=resolve(d);assert.deepEqual(r.timing_reconstruction.native_gap_validation.restored_notes,[]);
  assert.ok(r.notes.every(n=>n.status==='excluded'));assert.deepEqual(r.timing_reconstruction.warnings,d.timing_reconstruction.warnings);
});

test('one contradictory native frame cannot be hidden by a passing gap median',()=>{
  const d=measuredGapScene();
  // Keep the fitted gap equal to the median observed gap, while one certified
  // frame contradicts that constant gap outside both endpoint errors.
  d.scroll_motion.coordinate_registration.chunks[0].head_offsets[1].offset_pixels-=1.5;
  d.notes[1].points[2][1]+=8;d.head_registration.notes[1].observations[2].native_y_pixels+=8;
  assert.deepEqual(spacingFailures(d.notes,40,d.scroll_motion),[]);
  const warnings=spacingFailures(d.notes,40,d.scroll_motion,prepare(d,40));
  assert.ok(warnings.some(w=>w.comparison_basis==='native_endpoint_intervals'&&w.native_gap_measurements.status==='unresolved'));
});

test('another failed native check prevents partial source restoration',()=>{
  const d=failedSource();d.timing_reconstruction.warnings.push({note:0,reason:'shared_motion_observation_conflict'});
  const r=resolve(d);assert.equal(r.notes[0].status,'excluded');
  assert.ok(r.timing_reconstruction.warnings.some(w=>w.note===0&&w.reason==='shared_motion_observation_conflict'));
});

test('a play without any qualified clock retains the native gap diagnostic',()=>{
  const data=failedSource();data.notes.forEach(n=>{n.motion_clock=null;});
  const r=reconstruct({schema:1,data,reference:{status:'available',song_start_seconds:0,alignment_uncertainty_seconds:0},timing_text:text(template())});
  assert.equal(r.beat_timing.warnings[0].reason,'no_supported_note_targets');
  assert.deepEqual(r.timing_reconstruction.native_gap_validation.restored_notes,[]);
  assert.ok(r.timing_reconstruction.native_gap_validation.attempts.every(a=>a.reason==='source_clock_unavailable_or_stale'));
  assert.deepEqual(r.timing_reconstruction.warnings,data.timing_reconstruction.warnings);
});

test('endpoint gap bounds cannot hide a common absolute timing error',()=>{
  const d=nativeScene([[.85,0],[.95,1],[.6,2],[.7,3],[.8,4],[1,2],[1.1,3],[1.2,4]],40);
  d.head_registration={format:measuredGapScene().head_registration.format,notes:d.notes.map((n,i)=>({note:i,coordinate_method:'native_image_anchors',
    observations:n.points.map(([time,y])=>({time,source_pts_seconds:80+time,native_y_pixels:y,template:`generated-${i}`,
      native_cap_coordinate_uncertainty_pixels:1,native_cap_reference_scale_y:1}))}))};
  for(const i of [0,1])d.notes[i].target_seconds+=.025;
  const bad=spacingFailures(d.notes,40,d.scroll_motion,prepare(d,40)).filter(w=>w.peer_notes.join(',')==='0,1');
  assert.deepEqual(bad.map(w=>w.note).sort(),[0,1]);
  assert.ok(bad.every(w=>w.comparison_basis==='independent_registered_offsets'));
});

test('native gap resolution and reassociation work without a musical reference',()=>{
  const data=failedSource(),before=structuredClone(data),request={schema:1 as const,data,reference:{status:'unavailable',reason:'no_chart_reference'},timing_text:null};
  const r=reconstruct(request);assert.ok(r.notes.every(n=>n.status==='estimated'));
  assert.equal(r.beat_timing.warnings[0].reason,'beat_reference_unavailable');
  assert.deepEqual(derive('native-gaps',request),resolve(data));assert.deepEqual(data,before);
  const input={...data,...r,matches:[],unsupported_intervals:[],combo_events:[.85,1.1].map((t,i)=>({before:3+i,after:4+i,delta:1,
    lower_seconds:t,upper_seconds:t+.017,status:'candidate'}))};
  const script=`import json,sys
from piu_timeline.play.beats.timing import reassociate
s=json.load(sys.stdin);r=reassociate(s,0)
print(json.dumps({'matches':r['matches'],'reference_status':r['beat_timing']['status']}))`;
  const result=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{
    cwd:fileURLToPath(new URL('../../',import.meta.url)),input:JSON.stringify(input),encoding:'utf8'}));
  assert.equal(result.reference_status,'unavailable');assert.deepEqual(result.matches.map(m=>m.note).sort(),[0,1]);
});

for(const spacing of [20,40,80])for(const fps of [30,60,120])test(`clock conversion propagates prediction uncertainty: spacing=${spacing}, fps=${fps}`,()=>{
  const d=measuredGapScene(spacing,fps);
  d.notes[1].target_seconds+=.015;
  d.notes.forEach(n=>{n.motion_clock.residual=spacing/4;});
  const diagnostics=[];
  assert.deepEqual(spacingFailures(d.notes,spacing,d.scroll_motion,prepare(d,spacing),diagnostics),[]);
  const proof=diagnostics.find(p=>p.native_gap_measurements)?.native_gap_measurements;
  assert.ok(proof);assert.ok(proof.reconstructed_gap_pixels>proof.allowed_gap_range_pixels[1]);
  assert.ok(proof.prediction_range_pixels[0]<=proof.allowed_gap_range_pixels[1]);
  d.notes.forEach(n=>{n.motion_clock.residual=0;});
  assert.ok(spacingFailures(d.notes,spacing,d.scroll_motion,prepare(d,spacing)).length,
    'without measured slope error the incompatible target must fail');
});

test('prediction uncertainty cannot repair contradictory acquired gap intervals',()=>{
  const d=measuredGapScene(),w={peer_notes:[0,1],reconstructed_gap_pixels:60,
    prediction_uncertainty_pixels:100,visible_start_seconds:0,visible_end_seconds:2};
  d.notes[1].points[2][1]+=8;d.head_registration.notes[1].observations[2].native_y_pixels+=8;
  const proof=new NativeGapMeasurements(d).compare(w);
  assert.equal(proof.status,'unresolved');assert.ok(proof.allowed_gap_range_pixels[0]>proof.allowed_gap_range_pixels[1]);
  for(const error of [-1,Infinity,NaN]){
    const bad=new NativeGapMeasurements(d).compare({...w,prediction_uncertainty_pixels:error});
    assert.equal(bad.status,'unresolved');assert.equal(bad.reason,'invalid_prediction_uncertainty');
  }
});
