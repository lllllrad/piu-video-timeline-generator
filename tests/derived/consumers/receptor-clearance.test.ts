import test from 'node:test';
import assert from 'node:assert/strict';
import {fit} from '../../../src/piu_timeline/derived/clocks.ts';
import {nativeScene} from '../fixtures.ts';
import type {RecordData} from '../../../src/piu_timeline/derived/types.ts';

function scene(spacing=40,fps=60){
 const d=nativeScene([[1.2,0]],spacing,fps,5,{end:1.5,speedSpacingPerSecond:2}),receptor=d.layout.receptor_y*d.analysis_height;
 const points=d.scroll_motion.samples.map(p=>[p.time,receptor+2*spacing*(1.2-p.time)])
  .filter(([,y])=>receptor+.3*spacing<y&&y<receptor+.8*spacing);
 return {state:{...d.scroll_motion,height:d.analysis_height,spacing,
  samples:d.scroll_motion.samples.map(p=>({...p,lanes:5,displacement_basis:'independent_registered_peers'}))},
  track:{lane:0,note_index:0,points,coordinate_basis:'native_cap_center',registration_uncertainty_pixels:.025*spacing},
  receptor,layout:d.layout};
}
for(const spacing of[20,40,80])for(const fps of[30,60,120])
test(`registered moving caps near the receptor retain their observed target: spacing=${spacing}, fps=${fps}`,()=>{
 const s=scene(spacing,fps),before=structuredClone(s);
 assert.ok(s.track.points.every(([,y])=>y<s.receptor+.85*spacing));
 const result=fit(s.state,s.track,s.receptor,s.layout);
 assert.equal(result?.status,'estimated');assert.ok(Math.abs(result.target_seconds-1.2)<1e-8);
 assert.deepEqual(s,before);
});
for(const mode of['unregistered','stationary','crosses-row','duplicate-pts'])
test(`near-row observations require qualified moving source coordinates: ${mode}`,()=>{
 const s=scene();
 if(mode==='unregistered')delete s.track.coordinate_basis;
 if(mode==='stationary')s.track.points=s.track.points.map(([t])=>[t,s.receptor+20]);
 if(mode==='crosses-row')s.track.points=s.track.points.map(([t])=>[t,s.receptor+.5]);
 if(mode==='duplicate-pts'){const t=s.track.points[1][0],p=s.state.samples.find(p=>p.time===t);p.source_pts=s.state.samples.find(p=>p.time===s.track.points[0][0]).source_pts;}
 assert.equal(fit(s.state,s.track,s.receptor,s.layout),null);
});

test('near-row coordinates remain in the shared registration used by neighboring-note validation',async()=>{
 const {registered}=await import('../../../src/piu_timeline/derived/tracks.ts');
 const {spacingFailures}=await import('../../../src/piu_timeline/derived/beats/spacing.ts');
 const spacing=40,d=nativeScene([[1.2,0],[1.5,1],[1.7,2],[1.9,3],[2.1,4]],spacing,60,5,{end:2.4,speedSpacingPerSecond:2});
 const receptor=d.layout.receptor_y*d.analysis_height;
 const tracks=d.notes.map((n,i)=>({...n,note_index:i,coordinate_basis:'native_cap_center',registration_uncertainty_pixels:1}));
 tracks[0].points=d.scroll_motion.samples.map(p=>[p.time,receptor+80*(1.2-p.time)])
  .filter(([,y])=>receptor+12<y&&y<receptor+32);
 const motion:RecordData={...registered(tracks,d.scroll_motion.samples,d.analysis_height,spacing,receptor,.95*d.analysis_height),spacing,height:d.analysis_height};
 assert.ok(motion.coordinate_registration.chunks.some(c=>c.status==='fitted'&&c.head_offsets.some(h=>h.note===0)));
 const notes=tracks.map(t=>({...t,...fit(motion,t,receptor,d.layout)}));
 assert.equal(notes[0].status,'estimated');assert.ok(Math.abs(notes[0].target_seconds-1.2)<1e-8);
 assert.deepEqual(spacingFailures(notes,spacing,motion),[]);
});
