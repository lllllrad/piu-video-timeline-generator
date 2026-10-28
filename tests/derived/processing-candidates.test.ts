import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeScene} from './fixtures.ts';
import {candidates} from '../../src/piu_timeline/derived/candidates.ts';
import {recoverRows} from '../../src/piu_timeline/derived/recovery.ts';

function scene(spacing=40,fps=60){
 const d=nativeScene([[1,0],[1.08,1]],spacing,fps);
 Object.assign(d,{matches:[],combo_events:[],judgment_events:[{label:'PERFECT',delta:1,
  lower_seconds:1.035,upper_seconds:1.045,status:'candidate',detection_status:'candidate'}],
  median_frame_interval_seconds:1/fps,hold_analysis:{holds:[],unresolved_tracks:[]},
  visual_channels:{processing:{notes:[{note:0,status:'passed_target',passage_evidence:{
   range:[1.145,1.165],source_pts_seconds:[81.145,81.165]}}]},
   receptors:{events:[{lane:1,lit:true,frames:3,onset_range:[1.035,1.045],
    onset_source_pts_seconds:[81.035,81.045],start_seconds:1.045,end_seconds:1.08}]}}});
 return d;
}
const events=d=>d.judgment_events.map((e,event)=>({...e,source:'judgment',event}));
for(const spacing of [20,40,80])for(const fps of [30,60,120])test(`survival past a refresh excludes a competing candidate: spacing=${spacing}, fps=${fps}`,()=>{
 const d=scene(spacing,fps),before=structuredClone(d),[choices,rejected]=candidates(d,events(d));
 assert.ok(!choices[0]?.length,'a head still moving after the refresh cannot own it');
 assert.ok(rejected[0].includes('head_observed_after_refresh'));
 assert.equal(choices[1][0].alternative_rows,1);
 const [matches,recovered]=recoverRows(d);
 assert.deepEqual(recovered,[1]);assert.equal(matches[0].judgment_event,0);
 assert.deepEqual([matches[0].observation_lower_seconds,matches[0].observation_upper_seconds],[1.035,1.045]);
 assert.deepEqual(matches[0].lane_onset_source_pts_seconds,[81.035,81.045]);
 assert.deepEqual(d,before);
});
test('unverified, broad or insufficiently late passage does not erase a competing row',()=>{
 for(const mode of ['unverified','broad','nearby','other-note']){
  const d=scene(),p=d.visual_channels.processing.notes[0];
  if(mode==='unverified')p.status='unresolved';
  if(mode==='broad')p.passage_evidence.range=[1.145,1.245];
  if(mode==='nearby')p.passage_evidence.range=[1.12,1.14];
  if(mode==='other-note')p.note=2;
  const [choices]=candidates(d,events(d));
  assert.equal(choices[1][0].alternative_rows,2,mode);
  assert.deepEqual(recoverRows(d)[1],[],mode);
 }
});
