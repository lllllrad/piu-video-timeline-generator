import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeScene} from './fixtures.ts';
import {stitch} from '../../src/piu_timeline/derived/fragments.ts';

function scene(spacing=40,fps=60){
 const d=nativeScene([[1.2,0]],spacing,fps,5,{end:1.4});
 const points=d.notes[0].points,first={lane:0,points:points.filter(([t])=>t<=.45)},
  second={lane:0,points:points.filter(([t])=>.65<=t&&t<=1).map(([t,y])=>[t,y-.075*spacing])};
 const layout={...d.layout,combo_roi:[.05,.5,.4,.1]},receptor=layout.receptor_y*d.analysis_height;
 const boundary=.6*d.analysis_height+spacing;
 const last=first.points.filter(([,y])=>boundary<y).at(-1);last[1]+=.05*spacing;
 const motion={...d.scroll_motion,height:d.analysis_height,spacing,evidence_format:{method:'registered_peer_displacement'}};
 return {tracks:[first,second],receptor,spacing,motion,layout};
}
for(const spacing of [20,40,80])for(const fps of [30,60,120])test(`HUD continuation uses coherent registered observations, not a noisy endpoint: spacing=${spacing}, fps=${fps}`,()=>{
 const s=scene(spacing,fps),before=structuredClone(s),[tracks,origins]=stitch(s.tracks,s.receptor,s.spacing,s.motion,s.layout);
 assert.deepEqual(origins,[[0,1]]);
 assert.deepEqual(tracks[0].points,[...s.tracks[0].points,...s.tracks[1].points]);
 const proof=tracks[0].fragment_connections[0],truth=s.receptor+spacing*6*1.2;
 assert.ok(proof.common_offset_range_pixels[0]<=truth&&truth<=proof.common_offset_range_pixels[1]);
 for(const [records,error]of [[proof.references,proof.reference_error_pixels],[proof.reappearances,proof.continuation_error_pixels]])
  for(const r of records){
   assert.equal(r.source_pts_seconds,80+r.time);
   for(const offset of proof.common_offset_range_pixels)assert.ok(Math.abs(r.y+r.phase-offset)<=error+1e-8);
  }
 assert.deepEqual(s,before);
});
test('a different arrow, competing successors and a different lane stay separate',()=>{
 for(const mode of ['other-head','competing','lane','long-gap']){
  const s=scene();
  if(mode==='other-head')s.tracks[1].points=s.tracks[1].points.map(([t,y])=>[t,y+40]);
  if(mode==='competing')s.tracks.push(structuredClone(s.tracks[1]));
  if(mode==='lane')s.tracks[1].lane=1;
  if(mode==='long-gap')s.tracks[1].points=s.tracks[1].points.map(([t,y])=>[t+.4,y]);
  const [,origins]=stitch(s.tracks,s.receptor,s.spacing,s.motion,s.layout);
  assert.equal(origins.length,s.tracks.length,mode);
 }
});
test('contradictory registered references cannot fall back to a single endpoint',()=>{
 const s=scene(),time=s.tracks[0].points[0][0];
 s.motion.samples.find(p=>p.time===time).phase+=s.spacing;
 assert.deepEqual(stitch(s.tracks,s.receptor,s.spacing,s.motion,s.layout)[1],[[0],[1]]);
});
test('individually feasible reappearances still need one common anchor',()=>{
 const s=scene();
 s.tracks[1].points=s.tracks[1].points.map(([t,y],i)=>[t,y+(.075+(i===0?.2:i===1?-.2:0))*s.spacing]);
 assert.deepEqual(stitch(s.tracks,s.receptor,s.spacing,s.motion,s.layout)[1],[[0],[1]]);
});
