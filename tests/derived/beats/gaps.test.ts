import test from 'node:test';
import assert from 'node:assert/strict';
import {measuredGapScene,beatView} from '../fixtures.ts';
import {prepare,constrain} from '../../../src/piu_timeline/derived/beats/gaps.ts';
import {fitGrid} from '../../../src/piu_timeline/derived/beats/grid.ts';

function noisyClock(spacing:number,fps:number){
 const truth=[.59,.625,.6875,.75,.8125,.875];
 const d=measuredGapScene(spacing,fps,truth.map((t,i)=>[t,i%5]));
 d.notes.forEach((n,i)=>{
  n.target_seconds=truth[i]+.005;
  n.prediction_uncertainty_seconds=i?.023:.012;
  n.motion_target_phase=truth[i]*spacing*6;
  n.motion_clock={origin:.005,intercept:0,velocity:spacing*6,residual:spacing*6*.014,window:[.2,1.3]};
 });
 return {d,truth,group:{notes:truth.map((_,i)=>i)}};
}

for(const spacing of [20,40,80])for(const fps of [30,60,120])
test(`measured gaps preserve regular eighths beside an irregular object and broad clocks: spacing=${spacing}, fps=${fps}`,()=>{
 const {d,truth,group}=noisyClock(spacing,fps),before=structuredClone(d);
 const targets=d.notes.map(n=>n.target_seconds),errors=d.notes.map(n=>n.prediction_uncertainty_seconds);
 assert.equal(fitGrid(targets,errors,120,0).split,12,'point intervals alone admit the wrong coarser-looking mixture');
 const measured=prepare(d,[group]);assert.ok(measured.length);
 const gaps=measured.map(p=>({...p,indices:p.peer_notes}));
 const fit=fitGrid(targets,errors,120,0,undefined,0,[],[],gaps);
 assert.equal(fit.split,16);assert.equal(fit.status,'restored');assert.equal(fit.targets[0],.59375);
 assert.deepEqual(fit.targets.slice(1),truth.slice(1));assert.deepEqual(d,before);
 const result=beatView({schema:1,data:d,reference:{status:'available',song_start_seconds:0,alignment_uncertainty_seconds:0},
  timing_text:':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'.repeat(24)});
 assert.deepEqual(result.notes.slice(1).map(n=>n.target_seconds),truth.slice(1));
 assert.ok(result.notes.slice(1).every(n=>n.beat_reconstruction.status==='restored'));
 assert.ok(Math.abs(result.notes[0].target_seconds-truth[0])<=result.notes[0].prediction_uncertainty_seconds);
 assert.deepEqual(d,before);
});

for(const invalid of ['missing_error','different_clock','outside_window','reverse_clock','stale_clock'])
test(`unsupported clock/endpoint data cannot supply row-difference constraints: ${invalid}`,()=>{
 const {d,group}=noisyClock(40,60);
 for(const n of d.notes){
  if(invalid==='outside_window')n.motion_clock.window=[.2,.5];
  if(invalid==='reverse_clock')n.motion_clock.velocity=-240;
  if(invalid==='different_clock')n.motion_clock={...n.motion_clock,intercept:n.lane+.1};
  if(invalid==='stale_clock')n.motion_target_phase+=100;
 }
 if(invalid==='missing_error')for(const r of d.head_registration.notes)for(const o of r.observations)delete o.native_cap_coordinate_uncertainty_pixels;
 assert.deepEqual(prepare(d,[group]),[]);
});

test('signed differences constrain domains while an unsupported object cannot poison independent rows',()=>{
 const domains:[number,number][]=[[1,0],[1,3],[1,3],[10,10]],before=structuredClone(domains);
 const [result,proofs]=constrain(domains,.1,[{indices:[0,1],target_gap_range_seconds:[0,0]},
  {indices:[1,2],target_gap_range_seconds:[-.21,-.19]}]);
 assert.deepEqual(result,[[1,0],[3,3],[1,1],[10,10]]);
 assert.equal(proofs.length,1);assert.deepEqual(domains,before);
});
