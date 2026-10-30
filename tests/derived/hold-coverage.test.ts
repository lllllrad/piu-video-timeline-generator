import test from 'node:test';
import assert from 'node:assert/strict';
import {contracts} from '../../src/piu_timeline/derived/contracts.ts';
import {accountCapCoverage} from '../../src/piu_timeline/derived/hold_coverage.ts';
import {inspectionView as prepare,type InspectionFixture as PresentationInput} from './fixtures.ts';
import {nativeScene} from './fixtures.ts';
import type {RecordData} from '../../src/piu_timeline/derived/types.ts';

function scene():RecordData{
 const d=nativeScene([[1,0],[1.4,0]],40,60,5,{end:1.5}),time=.95,pts=80+time;
 const refs=[0,5,10].map(i=>80+d.notes[0].points[i][0]);
 const warning={note:0,tail_note:1,lane:0,image_connection_id:0,reason:'unresolved_hold_geometry',
  failure_detail:'known_hold_image_connection_not_observed_in_clear_frames',visible_start_seconds:time,visible_end_seconds:time,
  observed_points:1,image_evidence:[{time,source_pts:pts,missing_intervals_pixels:[[60,65]]}]};
 const cap={playback_seconds:time,source_pts_seconds:pts,intervals_pixels:[[58,68]],box_pixels:[50,80],score:.9,template_pose:0,
  native_lane_spacing_pixels:20,reference:{source_pts_seconds:refs[0],supporting_source_pts_seconds:refs,observed_y_range_pixels:[100,120]}};
 return {...d,matches:[],combo_events:[],judgment_events:[],coverage:{},
  hold_analysis:{holds:[{id:0,image_connection_id:0,lane:0,head_note:0,tail_note:1,covered_notes:[0,1],
   body_frames:8,start_range:[.99,1.01],end_range:[1.39,1.41],start_censored:false,end_censored:false,last_body_seconds:1.3,input:{segments:[]}}],unresolved_tracks:[warning]},
  visual_channels:{timeline:{frames:[...d.scroll_motion.samples.map(s=>[s.time,s.source_pts]),[time,pts]]},
   processing:{format:{cap_coverage:structuredClone(contracts.cap_coverage)},pixel_coordinates:{width:325,height:182},
    notes:[{note:0,status:'hold_component',cap_coverage:[cap]}]}}};
}
test('positive same-head cap pixels explain a missing endpoint region without a new press',()=>{
 const d=scene(),before=structuredClone(d),r=accountCapCoverage(d);
 assert.deepEqual(r.hold_analysis.unresolved_tracks,[]);assert.equal(r.hold_analysis.accounted_cap_coverage.length,1);
 assert.deepEqual(r.hold_analysis.accounted_cap_coverage[0].native_warning,d.hold_analysis.unresolved_tracks[0]);
 assert.deepEqual(r.matches,[]);assert.deepEqual(d,before);assert.deepEqual(accountCapCoverage(r),r);
});
test('a cap cannot explain a missing body outside its measured footprint',()=>{
 const d=scene();d.hold_analysis.unresolved_tracks[0].image_evidence[0].missing_intervals_pixels=[[60,90]];
 const r=accountCapCoverage(d),w=r.hold_analysis.unresolved_tracks[0];
 assert.deepEqual(w.image_evidence[0].missing_intervals_pixels,[[68,90]]);
 assert.deepEqual(r.hold_analysis.accounted_cap_coverage[0].native_warning,d.hold_analysis.unresolved_tracks[0]);
});
for(const mode of['unknown','wrong_pts','foreign_reference','stationary_reference','few_references','low_score','median_pose','duplicate_frame','different_hold','outside_box','oversized_box','wrong_format','unproven_body','invalid_missing_interval'])
test(`unverified cap evidence keeps the original geometry warning: ${mode}`,()=>{
 const d=scene(),r=d.visual_channels.processing.notes[0],p=r.cap_coverage[0];
 if(mode==='unknown')r.cap_coverage=[];
 if(mode==='wrong_pts')p.source_pts_seconds+=.001;
 if(mode==='foreign_reference')p.reference.supporting_source_pts_seconds[0]=99;
 if(mode==='stationary_reference')p.reference.observed_y_range_pixels=[100,101];
 if(mode==='few_references')p.reference.supporting_source_pts_seconds=p.reference.supporting_source_pts_seconds.slice(0,2);
 if(mode==='low_score')p.score=.5;
 if(mode==='median_pose')p.template_pose='median';
 if(mode==='duplicate_frame')r.cap_coverage.push(structuredClone(p));
 if(mode==='different_hold')d.hold_analysis.unresolved_tracks[0].image_connection_id=9;
 if(mode==='outside_box')p.intervals_pixels=[[40,68]];
 if(mode==='oversized_box')p.box_pixels=[0,150];
 if(mode==='unproven_body')d.hold_analysis.holds[0].body_frames=1;
 if(mode==='invalid_missing_interval')d.hold_analysis.unresolved_tracks[0].image_evidence[0].missing_intervals_pixels=[[65,60]];
 if(mode==='wrong_format')d.visual_channels.processing.format.cap_coverage.schema=9;
 const before=structuredClone(d),out=accountCapCoverage(d);
 assert.deepEqual(out.hold_analysis.unresolved_tracks,before.hold_analysis.unresolved_tracks);assert.deepEqual(d,before);
});
test('the report consumer retains cap measurements, their source warning and held-state semantics',()=>{
 const data=scene(),frames=data.scroll_motion.samples.map(s=>({playback_seconds:s.time,source_pts_seconds:s.source_pts,notes:[]}));
 const request:PresentationInput={schema:1,data,observations:{frames,visibility_frames:structuredClone(frames),occluders:[],native_body_risk_available:true,pre_hold_proofs:{}}};
 const view=prepare(request);
 assert.equal(view.hold_analysis.accounted_cap_coverage.length,1);
 assert.ok(!view.recognition_diagnostics.warnings.some(w=>w.failure_detail==='known_hold_image_connection_not_observed_in_clear_frames'));
 assert.equal(view.notes[0].requires_head_press,false);assert.deepEqual(view.matches,[]);
});
