import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';
import {assign} from '../../../src/piu_timeline/derived/frame_tracking.ts';
import {nativeScene,capFrames} from '../fixtures.ts';

const center=(y:number,error=.5)=>({yPixels:y,uncertaintyPixels:error,basis:{kind:'native_cap_center' as const}});
const anchor=(y:number,reference='cap')=>({yPixels:y,uncertaintyPixels:.5,
 basis:{kind:'image_reference_anchor' as const,reference:{kind:'template' as const,value:reference}}});
const observation=(time:number,y:number,reference='cap',raw=y)=>({time,center:center(y),anchor:anchor(raw,reference)});
const track=(y:number,time=1)=>({lane:0,observations:[observation(time,y)],maximumGapSeconds:.12});
const detection=(y:number,time=1+1/60)=>({lane:0,observation:observation(time,y)});
const motion=[{fromSeconds:1,pixels:8,uncertaintyPixels:.5}];

test('opaque image origins cannot swap two measured cap identities',()=>{
 const tracks=[track(200),track(240)],caps=[detection(192),detection(232)];
 tracks[0].observations[0].anchor=anchor(220,'old-a');tracks[1].observations[0].anchor=anchor(210,'old-b');
 caps[0].observation.anchor=anchor(244,'new-a');caps[1].observation.anchor=anchor(184,'new-b');
 const before=structuredClone({tracks,caps}),r=assign(tracks,caps,1+1/60,40,motion);
 assert.deepEqual(r.matches,[[0,0],[1,1]]);assert.deepEqual(r.ambiguities,[]);
 assert.deepEqual({tracks,caps},before);
});

test('a disappearing note cannot steal the following close note',()=>{
 const r=assign([track(200),track(216)],[detection(208)],1+1/60,40,motion);
 assert.deepEqual(r.matches,[[1,0]]);assert.deepEqual(r.ambiguities,[]);
});

test('coobserved separated caps preserve order while learning their first velocity',()=>{
 const r=assign([track(200),track(208)],[detection(199.5),detection(191.5)],1+1/60,40);
 assert.deepEqual(r.matches,[[0,1],[1,0]]);
 const asynchronous=[track(200,.99),track(208)];
 const ambiguous=assign(asynchronous,[detection(199.5),detection(191.5)],1+1/60,40);
 assert.deepEqual(ambiguous.matches,[]);assert.deepEqual(ambiguous.ambiguousTracks.sort(),[0,1]);
});

test('a unique global assignment can resolve an individually ambiguous candidate',()=>{
 const tracks=[track(200),track(208)];tracks[0].observations[0].center.uncertaintyPixels=8;
 const r=assign(tracks,[detection(192),detection(200)],1+1/60,40,motion);
 assert.deepEqual(r.matches.sort((a,b)=>a[0]-b[0]),[[0,0],[1,1]]);assert.deepEqual(r.ambiguities,[]);
});

test('equally feasible source identities remain an explicit ambiguity',()=>{
 const tracks=[track(200),track(202)];tracks.forEach(t=>t.observations[0].center.uncertaintyPixels=2);
 const r=assign(tracks,[detection(193)],1+1/60,40,motion);
 assert.deepEqual(r.matches,[]);assert.deepEqual(r.ambiguousTracks.sort(),[0,1]);assert.deepEqual(r.ambiguousDetections,[0]);
});

test('an identical image anchor can retain identity through a temporarily unregistered frame',()=>{
 const first=track(200);first.observations[0].anchor=anchor(214,'same-image');
 const next={lane:0,observation:{time:1+1/60,center:null,anchor:anchor(206,'same-image')}};
 assert.deepEqual(assign([first],[next],1+1/60,40,motion).matches,[[0,0]]);
 next.observation.anchor=anchor(206,'other-image');
 assert.deepEqual(assign([first],[next],1+1/60,40,motion).matches,[]);
});

test('pixel-qualified alternative anchors preserve identity when an unregistered representative changes',()=>{
 const first={lane:0,maximumGapSeconds:.12,observations:[{time:1,center:null,anchor:anchor(214,'a'),anchors:[anchor(214,'a'),anchor(200,'b')]}]};
 const next={lane:0,observation:{time:1+1/60,center:null,anchor:anchor(192,'b'),anchors:[anchor(206,'a'),anchor(192,'b')]}};
 assert.deepEqual(assign([first],[next],1+1/60,40,motion).matches,[[0,0]]);
 // A second positive view must agree; it is not a list of guesses to pick from.
 next.observation.anchors[0]=anchor(230,'a');
 assert.deepEqual(assign([first],[next],1+1/60,40,motion).matches,[]);
});

test('coordinate error widens the range while expired and cross-lane observations cannot attach',()=>{
 const next=detection(194);next.observation.center.uncertaintyPixels=2;
 assert.deepEqual(assign([track(200)],[next],1+1/60,40,motion).matches,[[0,0]]);
 next.observation.center.uncertaintyPixels=.1;
 assert.deepEqual(assign([track(200)],[next],1+1/60,40,motion).matches,[]);
 assert.deepEqual(assign([track(200)],[detection(192,1.2)],1.2,40,motion).matches,[]);
 assert.deepEqual(assign([track(200)],[{...detection(192),lane:1}],1+1/60,40,motion).matches,[]);
});

for(const displacement of [-10,0,6])test(`coobserved centers retain identities through a changed scroll step: ${displacement}`,()=>{
 const tracks=[track(200),track(280),{...track(240),lane:1}];
 // Earlier forward motion must not prevent a newly measured stop or reverse.
 tracks.forEach(t=>t.observations.unshift(observation(.98,t.observations[0].center.yPixels+8)));
 const caps=tracks.map(t=>({...detection(t.observations.at(-1).center.yPixels-displacement),lane:t.lane}));
 const r=assign(tracks,caps,1+1/60,40);
 assert.deepEqual(r.matches.sort((a,b)=>a[0]-b[0]),[[0,0],[1,1],[2,2]]);
 assert.deepEqual(r.ambiguities,[]);assert.ok(r.measuredDisplacement);
 assert.ok(r.measuredDisplacement.pixels-r.measuredDisplacement.uncertaintyPixels<=displacement);
 assert.ok(displacement<=r.measuredDisplacement.pixels+r.measuredDisplacement.uncertaintyPixels);
});

test('two equally supported scrolling translations do not become a measured displacement',()=>{
 const tracks=[track(200),{...track(200),lane:1}];
 const caps=[detection(192),detection(208),{...detection(192),lane:1},{...detection(208),lane:1}];
 const r=assign(tracks,caps,1+1/60,40);
 assert.equal(r.measuredDisplacement,null);assert.deepEqual(r.matches,[]);
 assert.deepEqual(r.ambiguousTracks.sort(),[0,1]);
});

test('a vanished lower cap cannot return as the following note after retained forward steps',()=>{
 const tracks=[track(125),track(250,1+5/60)],now=1+6/60;
 const steps=Array.from({length:5},(_,i)=>({fromSeconds:1+i/60,toSeconds:1+(i+1)/60,
  pixels:8,uncertaintyPixels:.5,basis:'forced_identity_images' as const}));
 const caps=[detection(242,now)];
 const result=assign(tracks,caps,now,40,[],steps);
 assert.deepEqual(result.matches,[[1,0]]);assert.deepEqual(result.ambiguities,[]);
 // A missing displacement link cannot be silently interpolated.
 const reappeared=[detection(77,now)];
 assert.deepEqual(assign([tracks[0]],reappeared,now,40,[],steps).matches,[[0,0]]);
 const broken=assign([tracks[0]],reappeared,now,40,[],steps.slice(1));
 assert.deepEqual(broken.matches,[]);
});

test('a lone new cap cannot reuse an old identity after an unobserved field interval',()=>{
 const previous=track(74,1),now=1+.117;
 const result=assign([previous],[detection(144,now)],now,64);
 assert.deepEqual(result.matches,[]);assert.equal(result.step,null);
 // Independent observed displacement can still bridge a visibility gap.
 const observed=assign([previous],[detection(44,now)],now,64,[{fromSeconds:1,pixels:30,uncertaintyPixels:1}]);
 assert.deepEqual(observed.matches,[[0,0]]);
});

for(const spacing of [20,40,80])for(const fps of [30,60,120])
test(`generated moving notes retain identity through missing and repeated views: spacing=${spacing}, fps=${fps}`,()=>{
 const scene=nativeScene(Array.from({length:7},(_,i)=>[.9+i*.125,0]),spacing,fps,5,{end:2.1,repeated:[[.65,.68]],dropped:[11]});
 const sources=scene.notes.map(n=>new Map<number,number>(n.points)),phases=new Map<number,number>(scene.scroll_motion.samples.map(s=>[s.time,s.phase]));
 let active:any[]=[];const created=new Map<number,number>();
 for(const [index,sample]of scene.scroll_motion.samples.entries()){
  const time=sample.time,caps=sources.flatMap((points,source)=>points.has(time)&&!(source===1&&index%17===0)?[{
   source,lane:0,observation:observation(time,points.get(time),`pose-${index%2}`,points.get(time)+(index%2?1:-1)*spacing/3)}]:[]);
  const times=new Set<number>(active.flatMap(t=>t.observations.map(o=>o.time)));
  const movements=[...times].map(fromSeconds=>({fromSeconds,pixels:sample.phase-phases.get(fromSeconds),uncertaintyPixels:spacing/80}));
  const r=assign(active,caps,time,spacing,movements);
  assert.deepEqual(r.ambiguousTracks,[]);
  const used=new Set<number>();
  for(const [i,j]of r.matches){
   assert.equal(active[i].source,caps[j].source,`identity switched at ${time}`);
   active[i].observations.push(caps[j].observation);active[i].observations=active[i].observations.slice(-6);used.add(j);
  }
  active=active.filter(t=>time-t.observations.at(-1).time<=.12);
  caps.forEach((cap,j)=>{if(!used.has(j)){created.set(cap.source,(created.get(cap.source)??0)+1);active.push({lane:0,source:cap.source,observations:[cap.observation],maximumGapSeconds:.12});}});
 }
 assert.equal(created.size,7);assert.ok([...created.values()].every(count=>count===1),'ordinary missing frames must not fragment a note');
});

for(const spacing of [20,40,80])for(const fps of [60,120])
test(`a cross-lane capture jump retains identities and an explicit cadence warning: spacing=${spacing}, fps=${fps}`,()=>{
 const tracks=[{...track(5*spacing),lane:0},{...track(7*spacing),lane:1}],time=1+1/fps,jump=spacing*.7;
 const caps=tracks.map(t=>({...detection(t.observations[0].center.yPixels-jump,time),lane:t.lane}));
 const before=structuredClone({tracks,caps}),r=assign(tracks,caps,time,spacing);
 assert.deepEqual(r.matches,[[0,0],[1,1]]);assert.deepEqual(r.ambiguities,[]);
 assert.equal(r.cadenceWarnings[0].reason,'observed_frame_step_exceeds_source_cadence');
 assert.deepEqual({tracks,caps},before);
 // One isolated cap cannot establish the cross-lane translation.
 assert.deepEqual(assign(tracks.slice(0,1),caps.slice(0,1),time,spacing).matches,[]);
 // A contradictory lane cannot certify an engine-time explanation.
 caps[1].observation.center.yPixels+=spacing;
 const conflict=assign(tracks,caps,time,spacing);assert.equal(conflict.measuredDisplacement,null);
});
test('ordinary capture steps do not acquire cadence warnings',()=>{
 const r=assign([track(200),{...track(240),lane:1}],[detection(192),{...detection(232),lane:1}],1+1/60,40);
 assert.deepEqual(r.matches,[[0,0],[1,1]]);assert.deepEqual(r.cadenceWarnings,[]);
});

test('the acquisition adapter retains cadence diagnostics with original source PTS',()=>{
 const script=String.raw`
import json
from piu_timeline.play.tracking import NoteTracker
layout={'receptor_y':.1,'note_y_max':.95,'lanes':[{'x':.1+i*.1}for i in range(5)]}
t=NoteTracker(layout,400,400)
t.update(1.,[{'lane':0,'y':.5},{'lane':1,'y':.7}],101.)
t.update(1.+1/60,[{'lane':0,'y':.43},{'lane':1,'y':.63}],101.+1/60)
print(json.dumps([{'lane':a.lane,'points':a.points,'warnings':a.tracking_warnings}for a in t.active]))
`;
 const result=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.equal(result.length,2);assert.ok(result.every(r=>r.points.length===2));
 for(const r of result){assert.equal(r.warnings[0].reason,'observed_frame_step_exceeds_source_cadence');
  assert.deepEqual(r.warnings[0].source_pts_seconds,[101,101+1/60]);}
});

for(const spacing of [20,40,80])for(const fps of [30,60,120])for(const burst of [false,true])
test(`generated production-style tracking learns its own movement across a capture burst: spacing=${spacing}, fps=${fps}, burst=${burst}`,()=>{
 const scene=capFrames(Array.from({length:9},(_,i)=>[1+Math.floor(i/2)*.125,i%2]),spacing,fps,
  burst?{end:2.3,repeated:[[.5,.5+1/fps]],renderTime:t=>t>=.7?t+2/fps:t}:{end:2.3});
 let active:any[]=[],steps:any[]=[];const created=new Map<number,number>(),uncertainSources=new Set<number>();let warnings=0;
 for(const [index,sample]of scene.frames.entries()){
  const time=sample.playback_seconds,caps=sample.notes.filter(n=>!(n.source===3&&index%17===0)).map(n=>({
   source:n.source,lane:n.lane,observation:observation(time,n.y_pixels)}));
  const r=assign(active,caps,time,spacing,[],steps);warnings+=r.cadenceWarnings.length;
  if(r.ambiguousTracks.length){
   assert.ok(r.translationAlternatives.length>1,`unexplained ambiguity at ${time}`);
   assert.ok(r.ambiguousDetections.length>0);
   warnings++;r.ambiguousTracks.forEach(i=>uncertainSources.add(active[i].source));
  }
  const used=new Set<number>();
  for(const [i,j]of r.matches){assert.equal(active[i].source,caps[j].source,`identity switched at ${time}`);
   active[i].observations.push(caps[j].observation);active[i].observations=active[i].observations.slice(-6);used.add(j);}
  active=active.filter((t,i)=>!r.ambiguousTracks.includes(i)&&time-t.observations.at(-1).time<=.12);
  caps.forEach((cap,j)=>{if(!used.has(j)){
   if(created.has(cap.source))assert.ok(uncertainSources.has(cap.source),`unexplained fragmentation at ${time}`);
   created.set(cap.source,(created.get(cap.source)??0)+1);
   active.push({lane:cap.lane,source:cap.source,observations:[cap.observation],maximumGapSeconds:.12});}});
  steps=steps.filter(s=>time-s.toSeconds<=.35);if(r.step)steps.push(r.step);
 }
 assert.equal(created.size,9);if(burst){if(spacing>=40||fps<=60)assert.ok(warnings>0);}
 else{assert.equal(uncertainSources.size,0);assert.ok([...created.values()].every(n=>n===1));}
});

test('a plausible slow reverse cannot steal the following row during a larger forward capture burst',()=>{
 const tracks=[{...track(308),lane:0},{...track(308),lane:1}],time=1+1/30,
  caps=[detection(260,time),detection(320,time),{...detection(260,time),lane:1},{...detection(320,time),lane:1}];
 const r=assign(tracks,caps,time,40);
 assert.deepEqual(r.matches,[]);assert.equal(r.translationAlternatives.length,2);
 assert.deepEqual(r.ambiguousTracks,[0,1]);assert.equal(r.ambiguousDetections.length,4);
});

test('one missing cap cannot make edges from different image translations look certain',()=>{
 const tracks=[0,1].flatMap(lane=>[148,208,268].map(y=>({...track(y),lane}))),time=1+1/30,
  caps=[...([132,192,252,312].map(y=>detection(y,time))),...[132,252,312].map(y=>({...detection(y,time),lane:1}))];
 const r=assign(tracks,caps,time,40);
 assert.equal(r.translationAlternatives.length,2);assert.deepEqual(r.matches,[]);
 assert.equal(r.ambiguousTracks.length,6);assert.equal(r.ambiguousDetections.length,7);
});

test('an unobserved final step cannot widen a disappeared cap into the following note',()=>{
 const old={lane:0,maximumGapSeconds:.12,observations:Array.from({length:6},(_,i)=>observation(1-(5-i)/30,32+8*(5-i)))},
  following={lane:0,maximumGapSeconds:.12,observations:[observation(1+2/30,46)]},now=1+3/30,
  steps=Array.from({length:2},(_,i)=>({fromSeconds:1+i/30,toSeconds:1+(i+1)/30,pixels:8,uncertaintyPixels:.5,basis:'forced_identity_images' as const}));
 const r=assign([old,following],[detection(38,now)],now,20,[],steps);
 assert.deepEqual(r.matches,[[1,0]]);assert.deepEqual(r.ambiguousTracks,[]);
});
