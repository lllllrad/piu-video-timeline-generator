import test from 'node:test';
import assert from 'node:assert/strict';
import {assign} from '../../../src/piu_timeline/derived/frame_tracking.ts';
import {nativeScene} from '../fixtures.ts';

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

test('coordinate error widens the range while expired and cross-lane observations cannot attach',()=>{
 const next=detection(194);next.observation.center.uncertaintyPixels=2;
 assert.deepEqual(assign([track(200)],[next],1+1/60,40,motion).matches,[[0,0]]);
 next.observation.center.uncertaintyPixels=.1;
 assert.deepEqual(assign([track(200)],[next],1+1/60,40,motion).matches,[]);
 assert.deepEqual(assign([track(200)],[detection(192,1.2)],1.2,40,motion).matches,[]);
 assert.deepEqual(assign([track(200)],[{...detection(192),lane:1}],1+1/60,40,motion).matches,[]);
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
