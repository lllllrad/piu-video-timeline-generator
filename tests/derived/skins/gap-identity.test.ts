import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';
import {assign}from '../../../src/piu_timeline/derived/frame_tracking.ts';

const position=(y:number,error:number)=>({yPixels:y,uncertaintyPixels:error,basis:{kind:'native_cap_center' as const}});
const observation=(time:number,y:number,error:number)=>({time,anchor:position(y,error),center:position(y,error)});
/** Independent native trajectories retain a hidden cap and two continuously visible peers. */
function scene(spacing:number,fps:number,kind:string){
 const time=1.3,frames=Math.round(.3*fps),error=spacing/80;
 const distance=(t:number)=>{
  const s=t-1;
  if(kind==='stop')return spacing*(s<.1?s: .1);
  if(kind==='reverse')return spacing*(s<.15?s:.3-s);
  if(kind==='acceleration')return spacing*(s+4*Math.max(0,s-.1)**2);
  return spacing*s;
 };
 const hidden={lane:0,maximumGapSeconds:.35,observations:Array.from({length:6},(_,i)=>{
  const t=1-(5-i)/fps;return observation(t,5*spacing-distance(t),error);
 })};
 const peers=[1,2].map(lane=>({lane,maximumGapSeconds:.35,observations:Array.from({length:frames},(_,i)=>{
  const t=1+i/fps;return observation(t,(7+lane)*spacing-distance(t),error);
 })}));
 const caps=[0,1,2].map(lane=>({lane,observation:observation(time,(lane?7+lane:5)*spacing-distance(time),error)}));
 const decoy={lane:0,observation:observation(time,caps[0].observation.center.yPixels-spacing*.45,error)};
 // This intentionally broad search interval admits both caps. It has no identity authority.
 const motion=[{fromSeconds:1,pixels:distance(time),uncertaintyPixels:spacing}];
 return {time,spacing,tracks:[hidden,...peers],caps,decoy,motion};
}

for(const spacing of [20,40,80])for(const fps of [30,60,120])for(const kind of ['slow','stop','reverse','acceleration'])
test(`direct independent endpoint travel resolves a gap: ${spacing}/${fps}/${kind}`,()=>{
 const s=scene(spacing,fps,kind),before=structuredClone(s);
 const r=assign(s.tracks,[s.decoy,...s.caps],s.time,spacing,s.motion);
 assert.deepEqual(r.matches,[[0,1],[1,2],[2,3]]);
 assert.deepEqual(r.ambiguousTracks,[]);
 assert.equal(r.gapConnections.length,1);
 const proof=r.gapConnections[0];assert.equal(proof.track,0);assert.equal(proof.detection,1);
 assert.deepEqual(proof.references.map(r=>r.lane),[1,2]);
 assert.equal(proof.fromSeconds,1);assert.equal(proof.toSeconds,s.time);
 assert.ok(proof.displacementRangePixels[1]-proof.displacementRangePixels[0]<=spacing/20+1e-6);
 assert.deepEqual(s,before);
});

for(const mode of ['no-peers','one-peer','missing-origin','peer-gap','conflicting-travel','true-cap-hidden'])
test(`a lone plausible cap cannot force a gap connection: ${mode}`,()=>{
 const s=scene(40,60,'slow');let caps=s.caps;
 if(mode==='no-peers'){s.tracks=s.tracks.slice(0,1);caps=caps.slice(0,1);}
 if(mode==='one-peer'){s.tracks=s.tracks.slice(0,2);caps=caps.slice(0,2);}
 if(mode==='missing-origin')s.tracks[1].observations.shift();
 if(mode==='peer-gap')s.tracks[1].observations.splice(1,5);
 if(mode==='conflicting-travel')s.tracks[1].observations[0]=observation(1,340, .5);
 if(mode==='true-cap-hidden')caps=[s.decoy,...caps.slice(1)];
 const r=assign(s.tracks,caps,s.time,s.spacing,s.motion);
 assert.ok(!r.matches.some(([i])=>i===0));assert.ok(r.ambiguousTracks.includes(0));
 assert.ok(r.ambiguousDetections.includes(0));assert.equal(r.gapConnections.length,0);
});

test('accumulating individually measured step errors is not direct gap evidence',()=>{
 const s=scene(40,60,'slow'),steps=Array.from({length:17},(_,i)=>({fromSeconds:1+i/60,toSeconds:1+(i+1)/60,
  pixels:2/3,uncertaintyPixels:1,basis:'coobserved_images' as const}));
 s.tracks[0].observations=s.tracks[0].observations.slice(-1);
 const r=assign([s.tracks[0]],[s.decoy],s.time,s.spacing,[],steps);
 assert.deepEqual(r.matches,[]);assert.deepEqual(r.ambiguousTracks,[0]);assert.equal(r.gapConnections.length,0);
});

test('the native adapter retains original observations and gap endpoint proof',()=>{
 const script=String.raw`
import json
from piu_timeline.play.tracking import NoteTracker
layout={'receptor_y':.1,'note_y_max':.95,'combo_roi':[0,.1,1,.8],'lanes':[{'x':.1+i*.1}for i in range(5)]}
t=NoteTracker(layout,400,800)
for i in range(-5,19):
 at=1+i/60
 lanes=[0,1,2]if i<=0 or i==18 else[1,2]
 t.update(at,[{'lane':lane,'y':(400+lane*40-i)/800}for lane in lanes],100+at)
a=next(a for a in t.active if a.lane==0)
print(json.dumps({'points':a.points,'connections':a.tracking_connections,'warnings':a.tracking_warnings}))
`;
 const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.equal(r.points.length,7);assert.deepEqual(r.points.at(-1),[1.3,382]);assert.deepEqual(r.warnings,[]);
 assert.equal(r.connections.length,1);const proof=r.connections[0];
 assert.equal(proof.source_pts_seconds,101.3);assert.equal(proof.fromSeconds,1);assert.equal(proof.toSeconds,1.3);
 assert.deepEqual(proof.references.map(p=>[p.lane,p.from.time,p.to.time,p.from.sourcePtsSeconds,p.to.sourcePtsSeconds]),
  [[1,1,1.3,101,101.3],[2,1,1.3,101,101.3]]);
});

for(const issue of ['duplicate','missing','retimed'])test(`source PTS cannot certify gap travel when ${issue}`,()=>{
 const s=scene(40,60,'slow');
 for(const t of s.tracks)for(const o of t.observations)o['sourcePtsSeconds']=100+o.time;
 for(const c of s.caps)c.observation['sourcePtsSeconds']=100+c.observation.time;
 const point=s.tracks[1].observations[3];
 if(issue==='duplicate')point['sourcePtsSeconds']=s.tracks[1].observations[2]['sourcePtsSeconds'];
 if(issue==='missing')delete point['sourcePtsSeconds'];
 if(issue==='retimed')point['sourcePtsSeconds']+=.001;
 const r=assign(s.tracks,s.caps,s.time,s.spacing,s.motion);
 assert.ok(!r.matches.some(([i])=>i===0));assert.ok(r.ambiguousTracks.includes(0));
});

test('greater matching coverage cannot erase another supported image translation',()=>{
 const tracks=[0,1,2].map(lane=>({lane,maximumGapSeconds:.12,observations:[observation(1,200,.5)]})),time=1+1/60;
 const caps=[0,1].map(lane=>({lane,observation:observation(time,192,.5)}));
 caps.push(...[0,1,2].map(lane=>({lane,observation:observation(time,208,.5)})));
 const r=assign(tracks,caps,time,40);
 assert.deepEqual(r.matches,[]);assert.equal(r.translationAlternatives.length,2);
 assert.deepEqual(r.ambiguousTracks,[0,1,2]);assert.equal(r.ambiguousDetections.length,5);
});
