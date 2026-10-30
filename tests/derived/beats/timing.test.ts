/** Beat application owns target decisions; input evidence remains unchanged. */
import test from 'node:test';import assert from 'node:assert/strict';
import {apply} from './fixtures.ts';
import {counters} from '../../../src/piu_timeline/derived/stages/associations.ts';
import {constantTempo,parse} from '../../../src/piu_timeline/derived/charts/ucs.ts';
import {MotionClock,clock} from '../../../src/piu_timeline/derived/clocks.ts';
test('reference application retains recording ranges and fails only the unsupported head',()=>{
 const d={notes:[10.001,10.124,10.251].map((target_seconds,lane)=>({status:'estimated',lane,points:[[9.9,200]],target_seconds,prediction_uncertainty_seconds:.003}))};
 const r=apply(d,10);assert.equal(r.beat_timing.status,'restored');assert.deepEqual(r.notes.map(n=>n.target_seconds),[10,10.125,10.25]);assert.equal(d.notes[0].target_seconds,10.001);assert.deepEqual(r.notes[0].video_target_range,[9.998,10.004]);
 d.notes[1].target_seconds=10.137;d.notes[1].prediction_uncertainty_seconds=.000001;const failed=apply(d,10);assert.equal(failed.beat_timing.status,'failed');assert.deepEqual(failed.notes.map(n=>n.target_seconds),[10,null,10.25]);assert.deepEqual(new Set(failed.beat_timing.warnings.map(w=>w.note)),new Set([1]));
});
test('input associations use restored targets and never failed notes',()=>{
 const notes=[{lane:0,status:'estimated',target_seconds:1,prediction_uncertainty_seconds:.01}],events=[{before:10,after:11,delta:1,lower_seconds:.99,upper_seconds:1.01,status:'candidate',reason:null}];
 const request={schema:1 as const,notes,events,display_delay_seconds:0,unsupported_intervals:[]};const r=counters(request).data;assert.deepEqual(r.matches.map(m=>m.note),[0]);assert.equal(r.matches[0].target_seconds,1);
 const failed=counters({...request,notes:[{...notes[0],status:'excluded',target_seconds:null,reason:'beat_timing_reconstruction_failed'}]});assert.deepEqual(failed.data.matches,[]);
});
test('constant catalogue tempo extends short template only with compatible official tempo',()=>{
 const d={notes:[{status:'estimated',lane:0,points:[[11,200]],target_seconds:12.125,prediction_uncertainty_seconds:.001}]},before=structuredClone(d),r=apply(d,10,{constant_tempo_bpm:'120'},8);
 assert.equal(r.beat_timing.status,'restored');assert.equal(r.notes[0].target_seconds,12.125);assert.equal(r.beat_timing.timing_extension.review_required,true);
 for(const bpm of ['120~240','121',null]){const f=apply(d,10,{constant_tempo_bpm:bpm},8);assert.equal(f.beat_timing.status,'failed');assert.equal(f.beat_timing.warnings[0].failure_detail,'outside_official_timing_sections');}
 assert.equal(constantTempo(parse(':Format=1\n:Mode=Single\n:BPM=120\n:Beat=4\n:Split=4\n.....\n:BPM=240\n.....\n'),'120'),false);assert.deepEqual(d,before);
});
function stopped(){return {spacing:40,height:400,strict_clock:true,samples:Array.from({length:121},(_,i)=>{const time=i/60;return {time,source_pts:800+time,phase:240*(time-Math.min(.1,Math.max(0,time-1))),chunk:0,variance:0,support:2,lanes:2};})};}
for(const [target,pause] of [[.95,0],[1.15,.1]])test(`fully observed moving crossing survives adjacent stop: ${target}`,()=>{
 const state=stopped(),before=structuredClone(state.samples),c=new MotionClock(state);assert.equal(clock(state.samples,40),null);
 const sample=state.samples.reduce((a,b)=>Math.abs(a.time-(target-.05))<Math.abs(b.time-(target-.05))?a:b),r=c.crossing(sample,240*(target-pause),.75);
 assert.ok(r);assert.ok(Math.abs(r.target_seconds-target)*240<=.75);assert.ok(r.motion_clock.residual<=.75);const [lo,hi]=r.motion_clock.window;
 if(pause)assert.ok(lo>=1.1-1/60-1e-8);else assert.ok(hi<=1+1/60+1e-8);
 const [a,b]=r.crossing_frame_seconds;assert.ok(lo<=a&&hi>=b&&hi-lo>=.3);assert.deepEqual(r.crossing_source_pts_seconds,[800+a,800+b]);assert.deepEqual(state.samples,before);
});
test('missing source frames inside crossing cannot be bridged by a flank',()=>{
 const state=stopped();state.samples=state.samples.filter(s=>!(.85<s.time&&s.time<1.04));const c=new MotionClock(state);assert.equal(c.crossing(c.at.get(.8),240*.95,.75),null);
});
