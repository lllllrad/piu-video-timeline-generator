import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeScene} from './fixtures.ts';
import {present} from '../../src/piu_timeline/derived/hold_presentation.ts';

function scene(spacing=40,fps=60){
 const frame=i=>.2+i/fps,origin=Math.round(.8*fps),b=origin+Math.max(1,Math.round(.04*fps));
 const first=[frame(origin-1),frame(origin)],second=[frame(b),frame(b+1)];
 const target=second[0]+second[1]-1,d=nativeScene([[1,0],[target,1]],spacing,fps,5,{end:1.4});
 const refresh=(range,label)=>({label,delta:1,lower_seconds:range[0],upper_seconds:range[1],status:'candidate',detection_status:'candidate'});
 Object.assign(d,{matches:[],combo_events:[],judgment_events:[refresh(first,'PERFECT'),refresh(second,'GOOD')],
  median_frame_interval_seconds:1/fps,hold_analysis:{holds:[],unresolved_tracks:[]},
  visual_channels:{timeline:{frames:d.scroll_motion.samples.map(s=>[s.time,s.source_pts])},
   note_types:{notes:d.notes.map((_,i)=>({note:i,observations:[{kind:'tap',role:'tap',playback_seconds:.5,source_pts_seconds:80.5}]}))},
   receptors:{events:[first,second].map((range,lane)=>({lane,lit:true,frames:3,onset_range:range,
    onset_source_pts_seconds:range.map(t=>80+t),start_seconds:range[1],end_seconds:range[1]+3/fps}))}}});
 return d;
}
for(const spacing of [20,40,80])for(const fps of [30,60,120])test(`independently recovered anchors unlock the next row: spacing=${spacing}, fps=${fps}`,()=>{
 const d=scene(spacing,fps),before=structuredClone(d),view=present(d);
 assert.deepEqual(view.matches.map(m=>m.note).sort(),[0,1]);
 for(const m of view.matches){
  const e=d.judgment_events[m.judgment_event],r=d.visual_channels.receptors.events[m.note];
  assert.deepEqual([m.observation_lower_seconds,m.observation_upper_seconds],[e.lower_seconds,e.upper_seconds]);
  assert.deepEqual(m.lane_onset_source_pts_seconds,r.onset_source_pts_seconds);
 }
 const again=present({...d,matches:structuredClone(view.matches)});
 assert.deepEqual(again.matches.map(m=>[m.note,m.judgment_event]),view.matches.map(m=>[m.note,m.judgment_event]));
 assert.deepEqual(d,before);
});
test('ambiguous rows cannot bootstrap each other without an independent seed',()=>{
 const d=scene();d.judgment_events.shift();d.visual_channels.receptors.events.shift();
 assert.deepEqual(present(d).matches,[]);
});
test('a new anchor cannot invent lane evidence for the next row',()=>{
 const d=scene();d.visual_channels.receptors.events.pop();
 assert.deepEqual(present(d).matches.map(m=>m.note),[0]);
});
test('a processing-conflicted proposal cannot unlock a later row',()=>{
 const d=scene();d.visual_channels.processing={notes:[{note:0,status:'passed_target',passage_evidence:{
  range:[1.09,1.11],source_pts_seconds:[81.09,81.11]}}]};
 d.matches=[{note:0,target_seconds:1,judgment_event:0,evidence_source:'judgment',observation_lower_seconds:d.judgment_events[0].lower_seconds,observation_upper_seconds:d.judgment_events[0].upper_seconds}];
 assert.deepEqual(present(d).matches,[]);
});
test('recovery does not depend on track-array order',()=>{
 const d=scene();d.notes.reverse();d.visual_channels.note_types.notes.reverse();
 d.visual_channels.note_types.notes.forEach((r,i)=>r.note=i);
 assert.deepEqual(present(d).matches.map(m=>[m.note,m.judgment_event]).sort(),[[0,1],[1,0]]);
});
