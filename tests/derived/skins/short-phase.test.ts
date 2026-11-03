import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';
import {nativeScene}from '../fixtures.ts';
import {MotionClock}from '../../../src/piu_timeline/derived/clocks.ts';

function scene(spacing=40,fps=60,frames=4){
 const d=nativeScene([[1,0]],spacing,fps,5,{end:1.3}),receptor=d.layout.receptor_y*d.analysis_height,
  timeline=d.scroll_motion.samples,last=Math.floor((.82-.2)*fps),observed=timeline.slice(last-3,last+1),
  selected=frames===2?[observed[0],observed.at(-1)]:observed,
  track={lane:0,points:selected.map(s=>[s.time,receptor+spacing*6*(1-s.time)]),coordinate_basis:'native_cap_center',
   registration_uncertainty_pixels:spacing/40,registration_offsets:{0:receptor+spacing*6}};
 return {d,track,receptor,state:{...d.scroll_motion,spacing,height:d.analysis_height,strict_clock:true}};
}
for(const spacing of [20,40,80])for(const fps of [30,60,120])for(const frames of [2,4])
test(`measured cap offsets use an independently covered phase crossing: spacing=${spacing}, fps=${fps}, frames=${frames}`,()=>{
 const {d,track,receptor,state}=scene(spacing,fps,frames),before=structuredClone({track,state}),r=new MotionClock(state).fit(track,receptor,d.layout);
 assert.ok(r);assert.ok(r.target_seconds-r.prediction_uncertainty_seconds<=1&&r.target_seconds+r.prediction_uncertainty_seconds>=1);
 assert.equal(r.native_motion_support.coordinate_basis,'native_cap_center');
 assert.deepEqual(r.native_motion_support.source_pts_seconds,track.points.map(([t])=>80+t));
 assert.ok(r.native_motion_support.position_errors_pixels.every(e=>Math.abs(e)<=2*track.registration_uncertainty_pixels));
 assert.deepEqual({track,state},before);
});
for(const kind of ['unqualified','zero_error','wrong_offset','one_bad_point','duplicate_pts','stationary'])
test(`short support cannot bypass contradictory or unqualified source evidence: ${kind}`,()=>{
 const {d,track,receptor,state}=scene();
 if(kind==='unqualified')track.coordinate_basis='image_reference_anchor';
 if(kind==='zero_error')track.registration_uncertainty_pixels=0;
 if(kind==='wrong_offset')track.registration_offsets[0]+=5;
 if(kind==='one_bad_point')track.points[1][1]+=6;
 if(kind==='duplicate_pts')state.samples.find(s=>s.time===track.points[1][0]).source_pts=80+track.points[0][0];
 if(kind==='stationary')for(const s of state.samples)s.phase=0;
 assert.equal(new MotionClock(state).fit(track,receptor,d.layout),null);
});
test('the native motion adapter transports qualification for a short registered approach',()=>{
 const script=String.raw`
import json
from piu_timeline.play.motion import ScrollMotion
from piu_timeline.play.tracking import Track
motion=ScrollMotion(400,40);motion.strict_clock=True
motion.samples=[{'time':.2+i/60,'source_pts':80.2+i/60,'phase':240*(.2+i/60),'chunk':0,'support':3,'variance':0}for i in range(67)]
track=Track(0,[(.75+i/60,40+240*(1-.75-i/60))for i in range(4)])
track.coordinate_basis='native_cap_center';track.registration_uncertainty_pixels=1.
print(json.dumps(motion.fit(track,40,{'note_y_max':.95})))
`;
 const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.equal(r.status,'estimated');assert.ok(r.native_motion_support);
 assert.ok(Math.abs(r.target_seconds-1)<=r.prediction_uncertainty_seconds);
});

test('registered restoration retains a short calibrated cap instead of its preliminary short-track exclusion',()=>{
 const script=String.raw`
import json
from piu_timeline.play.shared_timing import restore
from piu_timeline.play.tracking import Track,fit_track
layout={'receptor_y':.1,'note_y_max':.95,'lanes':[{'x':.1+i*.1}for i in range(5)]}
times=[.2+i/60 for i in range(79)]
tracks=[Track(0,[(times[i],40+240*(1-times[i]))for i in (34,36)])]
for lane,target in [(1,1.2),(2,1.35)]:tracks.append(Track(lane,[(t,40+240*(target-t))for t in times if 74<40+240*(target-t)<358]))
for track in tracks:track.coordinate_basis='native_cap_center';track.registration_uncertainty_pixels=1.
notes=[fit_track(t,40,40)for t in tracks]
_,diagnostics=restore(notes,tracks,[{'time':t,'source_pts':80+t}for t in times],layout,400,400)
print(json.dumps(notes[0]))
`;
 const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.equal(r.status,'estimated');assert.equal(r.reason,null);assert.ok(r.native_motion_support);
 assert.equal(r.native_motion_support.source_pts_seconds.length,2);
 assert.ok(Math.abs(r.target_seconds-1)<=r.prediction_uncertainty_seconds);
});

test('a static measured cap cannot acquire motion from nearby heads at the edge of the uncertainty budget',()=>{
 const {d,track,receptor,state}=scene(40,120,4);
 track.points=track.points.slice(0,2).map(([t])=>[t,receptor+40]);
 for(const s of state.samples)s.phase*=1.5;
 const phase=track.points.map(([t])=>state.samples.find(s=>s.time===t).phase);
 track.registration_offsets[0]=receptor+40+(phase[0]+phase[1])/2;
 assert.equal(new MotionClock(state).fit(track,receptor,d.layout),null);
});
