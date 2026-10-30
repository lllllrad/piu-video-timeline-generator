import test from 'node:test';import assert from 'node:assert/strict';
import {MotionClock,clock} from '../../../src/piu_timeline/derived/clocks.ts';
import {near} from '../beats/fixtures.ts';
function scene(sparse=false){return {height:400,spacing:40,strict_clock:true,samples:Array.from({length:601},(_,i)=>{const time=i/60;return {time,source_pts:800+time,phase:240*time+(time>=5?9:0),chunk:0,variance:0,support:2,lanes:2};}).filter(s=>!sparse||!(5<s.time&&s.time<6.02)||[318,330,331].includes(Math.round(s.time*60)))};}
test('local clock retains observed crossing after rejecting remote block average',()=>{
 const s=scene(),before=structuredClone(s),m=new MotionClock(s),r=m.crossing(m.at.get(5.3),240*5.516+9,.75);
assert.ok(r);
assert.equal(r.fit_method,'shared_scroll_clock');
assert.ok(near(r.target_seconds,5.516));
assert.deepEqual(r.crossing_frame_seconds,[5.5,331/60]);
assert.deepEqual(r.crossing_source_pts_seconds,[805.5,800+331/60]);
const [lo,hi]=r.crossing_capture_range;
assert.ok(r.rejected_chunk_clock.target_seconds>hi);
assert.ok(lo<=r.target_seconds&&r.target_seconds<=hi);
assert.ok(r.motion_clock.window[0]>5);
assert.deepEqual(s,before);
});
test('sparse local support cannot replace rejected block average',()=>{const s=scene(true),m=new MotionClock(s);assert.ok(clock(s.samples,40));assert.equal(m.crossing(m.at.get(5.3),240*5.516+9,.75),null);});
test('crossing inside capture-phase jump retains frame bounds and explicit unresolved clock',()=>{const m=new MotionClock(scene()),r=m.crossing(m.at.get(4.8),1208,.75);assert.equal(r.fit_method,'shared_scroll_frame_bounds');assert.equal(r.motion_clock,null);assert.equal(r.native_clock_warning.reason,'shared_subframe_clock_unresolved');assert.deepEqual(r.crossing_frame_seconds,[299/60,5]);});
test('remote repeated frames do not erase locally supported crossing or invent stationary clock',()=>{
 const s={height:400,spacing:40,strict_clock:true,samples:Array.from({length:121},(_,i)=>{const time=i/60;return {time,source_pts:800+time,phase:240*(time-Math.min(.2,Math.max(0,time-.2))),chunk:0,variance:0,support:2,lanes:2};})},before=structuredClone(s),m=new MotionClock(s);assert.equal(clock(s.samples,40),null);
 const r=m.crossing(m.at.get(.5),240*(.65-.2),.75);
assert.ok(r);
assert.ok(Math.abs(r.target_seconds-.65)<=r.prediction_uncertainty_seconds);
assert.ok(r.motion_clock.residual<=.75);
assert.ok(Math.abs(r.target_seconds-.65)*240<=.75);
assert.equal(r.motion_clock.selection,'precision_then_native_support');
assert.ok(r.motion_clock.trimmed_outer_frames>0);
assert.ok(r.motion_clock.window[0]>.2);
assert.ok(r.motion_clock.window[1]-r.motion_clock.window[0]>=.3);
assert.deepEqual(r.crossing_source_pts_seconds,[800+38/60,800+.65]);
 const bounded=m.crossing(m.at.get(.1),48,.75);assert.equal(bounded.motion_clock,null);assert.ok(bounded.prediction_uncertainty_seconds>.1);assert.ok(bounded.native_clock_warning);assert.deepEqual(s,before);
 s.samples=s.samples.filter(s=>!(.4<s.time&&s.time<.9)||[.5,38/60,.65].includes(s.time));const sparse=new MotionClock(s);assert.equal(sparse.crossing(sparse.at.get(.5),240*(.65-.2),.75),null);
});
