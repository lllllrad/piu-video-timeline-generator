import test from 'node:test';
import assert from 'node:assert/strict';
import {associate} from '../../src/piu_timeline/derived/association.ts';
import {nativeScene} from './fixtures.ts';
import {interleaved,stitch} from '../../src/piu_timeline/derived/fragments.ts';

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

function contained(spacing=40,fps=60){
 const d=nativeScene([[1.2,0],[1.1,1]],spacing,fps,5,{end:1.4}),all=d.notes[0].points;
 const inner=all.filter(([t])=>.6-1e-9<=t&&t<=.7+1e-9),selected=new Set(inner.map(p=>p[0]));
 const outer=all.filter(([t])=>!selected.has(t));
 return {tracks:[{lane:0,points:outer},{lane:0,points:inner}],spacing,
  motion:{...d.scroll_motion,evidence_format:{method:'registered_peer_displacement'}},truth:d.layout.receptor_y*d.analysis_height+spacing*6*1.2};
}
for(const spacing of[20,40,80])for(const fps of[30,60,120])test(`a contained same-head fragment retains all captured positions: spacing=${spacing}, fps=${fps}`,()=>{
 const s=contained(spacing,fps),before=structuredClone(s),[tracks,origins]=interleaved(s.tracks,spacing,s.motion);
 assert.deepEqual(origins,[[0,1]]);assert.deepEqual(tracks[0].points,[...s.tracks[0].points,...s.tracks[1].points].sort((a,b)=>a[0]-b[0]));
 const proof=tracks[0].fragment_connections[0];assert.equal(proof.method,'joint_interleaved_native_bands');
 assert.ok(proof.common_offset_range_pixels[0]<=s.truth&&s.truth<=proof.common_offset_range_pixels[1]);
 for(const p of proof.references){assert.equal(p.source_pts_seconds,80+p.time);for(const offset of proof.common_offset_range_pixels)assert.ok(Math.abs(p.y+p.phase-offset)<=proof.reference_error_pixels+1e-8);}
 assert.deepEqual(s,before);
});
for(const mode of['same-frame','other-cap','competing-owner','wrong-lane','missing-frame','failed-chunk','stationary','missing-pts','duplicate-pts','insufficient-shared-chunk'])
test(`a contained fragment without unique native identity stays separate: ${mode}`,()=>{
 const s=contained();
 if(mode==='same-frame'){s.tracks[0].points.push([...s.tracks[1].points[2]]);s.tracks[0].points.sort((a,b)=>a[0]-b[0]);}
 if(mode==='other-cap')s.tracks[1].points=s.tracks[1].points.map(([t,y])=>[t,y+.13*s.spacing]);
 if(mode==='competing-owner')s.tracks.push(structuredClone(s.tracks[1]));
 if(mode==='wrong-lane')s.tracks[1].lane=1;
 if(mode==='missing-frame')s.motion.samples=s.motion.samples.filter(p=>p.time!==s.tracks[1].points[2][0]);
 if(mode==='missing-pts')delete s.motion.samples.find(p=>p.time===s.tracks[1].points[0][0]).source_pts;
 if(mode==='duplicate-pts'){const times=s.tracks[1].points.slice(0,2).map(p=>p[0]);const first=s.motion.samples.find(p=>p.time===times[0]);s.motion.samples.find(p=>p.time===times[1]).source_pts=first.source_pts;}
 if(mode==='insufficient-shared-chunk'){const outer=new Set(s.tracks[0].points.slice(2).map(p=>p[0]));s.motion.samples.forEach(p=>{if(outer.has(p.time))p.chunk=1;});}
 if(mode==='failed-chunk')s.motion.coordinate_failures={0:'unreliable_peer_motion'};
 if(mode==='stationary'){
  s.motion.samples.forEach(p=>{p.phase=0;});s.tracks.forEach(t=>{t.points=t.points.map(([time])=>[time,s.truth]);});
 }
 assert.equal(interleaved(s.tracks,s.spacing,s.motion)[0].length,s.tracks.length);
});

test('interleaved fragments with individually permitted errors still need one common offset',()=>{
 const d=nativeScene([[1.2,0]],40,60,5,{end:1.4}),points=d.notes[0].points;
 const first=points.filter(([t],i)=>t<=.7+1e-9&&(t<.6-1e-9||i%2===0)).map(p=>[...p]);
 const second=points.filter(([t],i)=>t>=.6-1e-9&&(t>.7+1e-9||i%2!==0)).map(([t,y])=>[t,y+4]);
 first[0][1]-=5.6;second.at(-1)[1]+=5.6;
 assert.deepEqual(interleaved([{lane:0,points:first},{lane:0,points:second}],40,
  {...d.scroll_motion,evidence_format:{method:'registered_peer_displacement'}})[1],[[0],[1]]);
});

test('a contained identity uses the shared motion origin without discarding an earlier chunk',()=>{
 const s=contained(),first=s.tracks[0].points[0][0];
 const sample=s.motion.samples.find(p=>p.time===first);sample.chunk=1;sample.phase+=5*s.spacing;
 const before=structuredClone(s),[tracks,origins]=interleaved(s.tracks,s.spacing,s.motion);
 assert.deepEqual(origins,[[0,1]]);assert.ok(tracks[0].points.some(([t])=>t===first));
 const proof=tracks[0].fragment_connections[0];assert.equal(proof.chunk,0);
 assert.ok(!proof.references.some(p=>p.time===first));assert.equal(proof.references.length,tracks[0].points.length-1);
 assert.ok(proof.common_offset_range_pixels[0]<=s.truth&&s.truth<=proof.common_offset_range_pixels[1]);
 assert.deepEqual(s,before);
});

test('restoring one physical head removes a false same-lane chord conflict',()=>{
 const d=nativeScene([[1.25,0],[1.25,1],[1.25,2]],40,60,5,{end:1.4}),all=d.notes[0].points;
 const inside=new Set(all.filter(([t])=>.6-1e-9<=t&&t<=.7+1e-9).map(p=>p[0]));
 const source=[{lane:0,points:all.filter(([t])=>!inside.has(t))},{lane:0,points:all.filter(([t])=>inside.has(t))},
  ...d.notes.slice(1).map(n=>({lane:n.lane,points:n.points}))];
 const timed=tracks=>tracks.map(t=>({...d.notes.find(n=>n.lane===t.lane),points:t.points}));
 const event={status:'candidate',delta:1,lower_seconds:1.25,upper_seconds:1.25+1/60};
 assert.deepEqual(associate(timed(source),[{...event}]),[],'two identities for the same cap incorrectly conflict inside the chord');
 const[tracks,origins]=stitch(source,d.layout.receptor_y*d.analysis_height,40,
  {...d.scroll_motion,evidence_format:{method:'registered_peer_displacement'}},d.layout);
 assert.equal(tracks.length,3);assert.deepEqual(origins,[[0,1],[2],[3]]);
 const matches=associate(timed(tracks),[{...event}]);assert.equal(matches.length,3);
 assert.ok(matches.every(m=>m.combo_event===0&&m.row_note_count===3));
 assert.equal(tracks.reduce((n,t)=>n+t.points.length,0),source.reduce((n,t)=>n+t.points.length,0));
});
