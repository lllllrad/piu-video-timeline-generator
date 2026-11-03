import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {nativeScene} from '../fixtures.ts';
import {registered} from '../../../src/piu_timeline/derived/tracks.ts';
import {MotionClock} from '../../../src/piu_timeline/derived/clocks.ts';

function scene(spacing=40,fps=60){
 const d=nativeScene([[1,0]],spacing,fps,5,{end:1.3});
 const track={lane:0,points:d.notes[0].points,coordinate_basis:'native_cap_center',registration_uncertainty_pixels:spacing/40};
 return {d,track,spacing,receptor:d.layout.receptor_y*d.analysis_height,bottom:d.layout.note_y_max*d.analysis_height};
}

for(const spacing of [20,40,80])for(const fps of [30,60,120])
test(`one measured cap supplies displacement and a bounded target: spacing=${spacing}, fps=${fps}`,()=>{
 const {d,track,receptor,bottom}=scene(spacing,fps),before=structuredClone(track);
 const result=registered([track],d.scroll_motion.samples,d.analysis_height,spacing,receptor,bottom);
 assert.ok(result.samples.some(s=>s.displacement_basis==='measured_cap_displacement'));
 assert.ok(result.coordinate_registration.chunks.some(c=>c.status==='fitted'&&c.heads===1));
 const offsets=Object.fromEntries(result.coordinate_offsets.map(([i,chunk,y])=>[chunk,y]));
 const clock=new MotionClock({...result,spacing,height:d.analysis_height});
 const fit=clock.fit({...track,registration_offsets:offsets},receptor,d.layout);
 assert.ok(fit,'the measured approach supports a target without another simultaneous note');
 assert.ok(fit.target_seconds-fit.prediction_uncertainty_seconds<=1+1e-9);
 assert.ok(fit.target_seconds+fit.prediction_uncertainty_seconds>=1-1e-9);
 assert.ok(fit.prediction_uncertainty_seconds<.05);
 assert.deepEqual(track,before);
});

for(const corruption of ['unregistered','no_error','nonfinite_error'])
test(`an unsupported solo image origin cannot create a shared clock: ${corruption}`,()=>{
 const {d,track,spacing,receptor,bottom}=scene();
 if(corruption==='unregistered')track.coordinate_basis='image_reference_anchor';
 if(corruption==='no_error')track.registration_uncertainty_pixels=0;
 if(corruption==='nonfinite_error')track.registration_uncertainty_pixels=NaN;
 const result=registered([track],d.scroll_motion.samples,d.analysis_height,spacing,receptor,bottom);
 assert.ok(result.samples.every(s=>s.support===0));
 assert.ok(result.coordinate_registration.chunks.every(c=>c.status!=='fitted'));
 assert.equal(new MotionClock({...result,spacing,height:d.analysis_height}).fit(track,receptor,d.layout),null);
});

test('a measured solo cap retains source capture plateaus and gaps',()=>{
 const {d,track,spacing,receptor,bottom}=scene();
 const original=structuredClone(track.points);
 for(let i=1;i<track.points.length;i+=2)track.points[i][1]=track.points[i-1][1];
 const result=registered([track],d.scroll_motion.samples,d.analysis_height,spacing,receptor,bottom);
 assert.ok(result.samples.some(s=>s.support===1&&s.observed_peer_displacement_pixels===0));
 const times=new Set(d.scroll_motion.samples.map(s=>s.source_pts));
 assert.ok(result.samples.every(s=>times.has(s.source_pts)));
 assert.deepEqual(track.points.map(p=>p[0]),original.map(p=>p[0]));
});

for(const motion of ['stopped','reverse'])test(`a measured solo ${motion} cannot supply a forward target`,()=>{
 const {d,track,spacing,receptor,bottom}=scene();
 const low=track.points.at(-1)[1],high=track.points[0][1];
 track.points=track.points.map(([t,y])=>[t,motion==='stopped'?(low+high)/2:low+high-y]);
 const result=registered([track],d.scroll_motion.samples,d.analysis_height,spacing,receptor,bottom);
 assert.equal(new MotionClock({...result,spacing,height:d.analysis_height}).fit(track,receptor,d.layout),null);
});

for(const spacing of [20,40,80])for(const fps of [30,60,120])
test(`opposite permitted endpoint errors cannot disconnect a measured scroll clock: spacing=${spacing}, fps=${fps}`,()=>{
 const d=nativeScene([[1,0],[1.1,1]],spacing,fps,5,{end:1.3}),error=spacing/40,
  receptor=d.layout.receptor_y*d.analysis_height,bottom=d.layout.note_y_max*d.analysis_height;
 const tracks=d.notes.map((n,i)=>({lane:n.lane,coordinate_basis:'native_cap_center',registration_uncertainty_pixels:error,
  points:n.points.map(([t,y])=>[t,y+(Math.round((t-.2)*fps)%2?1:-1)*(i?1:-1)*error])}));
 const before=structuredClone(tracks),r=registered(tracks,d.scroll_motion.samples,d.analysis_height,spacing,receptor,bottom);
 assert.deepEqual(r.coordinate_failures,{});assert.deepEqual(r.coordinate_conflicts,[]);
 const visible=tracks.flatMap(t=>t.points.filter(([,y])=>receptor+.85*spacing<y&&y<bottom-.55*spacing).map(([t])=>t)),
  lo=Math.min(...visible),hi=Math.max(...visible),continuous=r.samples.filter(s=>lo<=s.time&&s.time<=hi);
 assert.equal(new Set(continuous.map(s=>s.chunk)).size,1);
 assert.ok(continuous.slice(1).every(s=>s.support>0&&s.native_displacement_interval));
 for(const s of continuous.slice(1)){
  const previous=r.samples[r.samples.indexOf(s)-1],truth=spacing*6*(s.time-previous.time),range=s.native_displacement_interval.range_pixels;
  assert.ok(range[0]-1e-8<=truth&&truth<=range[1]+1e-8);
 }
 assert.deepEqual(tracks,before);
});

test('contradictory certified movements remain explicit instead of choosing a convenient peer',()=>{
 const {d,track,spacing,receptor,bottom}=scene(),other=structuredClone(track);other.lane=1;
 other.points=other.points.map(([t,y],i)=>[t,y+40+(i%2?8:-8)]);
 const before=structuredClone([track,other]),r=registered([track,other],d.scroll_motion.samples,d.analysis_height,spacing,receptor,bottom);
 assert.ok(r.coordinate_conflicts.some(w=>w.reason==='native_frame_displacement_conflict'&&w.failure_detail==='inconsistent_native_displacements'));
 assert.ok(r.samples.some(s=>s.support===0));assert.deepEqual([track,other],before);
});

test('the native adapter transports measured-center qualification into shared motion',()=>{
 const script=String.raw`
import json
from piu_timeline.play.tracking import Track
from piu_timeline.play.shared_timing import registered_motion
layout={'receptor_y':.1,'note_y_max':.95,'lanes':[{'x':.1+i*.1}for i in range(5)]}
times=[.2+i/60 for i in range(64)]
track=Track(0,[(t,40+240*(1-t))for t in times if 74<40+240*(1-t)<358])
track.coordinate_basis='native_cap_center';track.registration_uncertainty_pixels=1.
motion=registered_motion([track],[{'time':t,'source_pts':80+t}for t in times],400,40,40,380)
fit=motion.fit(track,40,layout)
print(json.dumps({'basis':sorted(set(s['displacement_basis']for s in motion.samples)),
 'fit':fit,'source_pts':[s['source_pts']for s in motion.samples]}))
`;
 const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.ok(r.basis.includes('measured_cap_displacement'));
 assert.ok(Math.abs(r.fit.target_seconds-1)<r.fit.prediction_uncertainty_seconds);
 assert.equal(r.source_pts[0],80.2);
});

test('independent native lanes retain a measured capture jump without calling it ordinary elapsed motion',()=>{
 const spacing=40,scene=nativeScene([[1,0],[1.1,1]],spacing,60,5,{end:1.3,renderTime:t=>t>=.7?t+5/60:t}),
  receptor=scene.layout.receptor_y*scene.analysis_height,bottom=scene.layout.note_y_max*scene.analysis_height,
  tracks=scene.notes.map(n=>({lane:n.lane,points:n.points,coordinate_basis:'native_cap_center',registration_uncertainty_pixels:1})),
  r=registered(tracks,scene.scroll_motion.samples,scene.analysis_height,spacing,receptor,bottom);
 assert.ok(r.coordinate_conflicts.some(w=>w.reason==='native_motion_cadence_unresolved'));
 assert.ok(!r.coordinate_conflicts.some(w=>w.failure_detail==='excessive_frame_displacement'));
 const before=r.samples.find(s=>Math.abs(s.time-(.7-1/60))<1e-8),after=r.samples.find(s=>Math.abs(s.time-.7)<1e-8);
 assert.equal(before.chunk,after.chunk);assert.ok(after.support>=2);
 assert.ok(after.native_displacement_interval.range_pixels[0]<=24&&after.native_displacement_interval.range_pixels[1]>=24);
});
