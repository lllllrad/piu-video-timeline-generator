/** Generic native-coordinate fixtures; no recording- or song-specific cases. */
import type {RecordData} from '../../../src/piu_timeline/derived/types.ts';
import {beatView} from '../fixtures.ts';
export const near=(a:number,b:number,error=1e-7)=>Math.abs(a-b)<=error;
export function coordinates():RecordData{
 const times=Array.from({length:10},(_,i)=>.5+i*.02);
 const notes=Array.from({length:9},(_,i)=>({lane:i%3,status:'estimated',target_seconds:1+i*.125,
  points:times.map(t=>[t,40+240*(1+i*.125-t)]),motion_clock:{origin:0,velocity:i===4?244:240,intercept:0},motion_target_phase:240*(1+i*.125)}));
 return {analysis_height:600,layout:{receptor_y:40/600},notes,
  head_registration:{notes:notes.map((_,i)=>({note:i,status:'registered',coordinate_method:'native_cap_measurements',observations:times.map(time=>({time}))}))},
  scroll_motion:{samples:times.map(time=>({time,source_pts:80+time,phase:240*time,chunk:0})),coordinate_registration:{chunks:[{chunk:0,status:'fitted',
   head_offsets:notes.map((_,i)=>({note:i,offset_pixels:40+240*(1+i*.125)}))}]}}};
}
export function domain():RecordData{
 const data=coordinates();data.analysis_width=400;data.layout.lanes=Array.from({length:3},(_,i)=>({x:.1+.1*i}));
 data.notes.forEach((n,i)=>n.prediction_uncertainty_seconds=i===4?.13:.001);return data;
}
export function chord():RecordData{
 const times=Array.from({length:9},(_,i)=>.6+i*.01),values=[[1.001,.006,1],[1.02,.03,1],[1.03125,.002,1.03125]];
 return {notes:values.map(([target,error,actual],i)=>({lane:i,status:'estimated',target_seconds:target,prediction_uncertainty_seconds:error,
  points:times.map(t=>[t,40+500*(actual-t)])})),head_registration:{notes:values.map((_,i)=>({note:i,status:'registered',coordinate_method:'native_cap_measurements',
  coordinate_uncertainty_pixels:1,observations:times.map(time=>({time,source_pts_seconds:50+time}))}))},analysis_width:400,analysis_height:400,
  layout:{receptor_y:.1,lanes:values.map((_,i)=>({x:.2+.1*i}))}};
}
export function spatial():RecordData{
 const times=Array.from({length:8},(_,i)=>.4+i/60),targets=[1.007,1.507],velocities=[120,240];
 const notes=targets.map((target,i)=>({status:'estimated',lane:i,points:times.map(t=>[t,180+60*i-240*(t-.4)]),target_seconds:target,
  motion_target_phase:target*velocities[i],motion_clock:{origin:0,velocity:velocities[i],intercept:0}}));
 return {notes,motion:{samples:times.map(time=>({time,chunk:0})),coordinate_registration:{chunks:[{chunk:0,status:'fitted',head_offsets:[{note:0,offset_pixels:220},{note:1,offset_pixels:280}]}]}},
  groups:[{notes:[0,1],targets,errors:[.01,.01],bpm:120,origin:0}]};
}
export function stagger(gap=4):RecordData{
 const times=Array.from({length:9},(_,i)=>i/60),clock={origin:0,velocity:500,intercept:0};
 const notes=[1,1+gap/500].map((target,i)=>({lane:i,status:'estimated',target_seconds:target,fit_method:'shared_scroll_clock',motion_clock:clock,
  motion_target_phase:500*target,points:times.map(t=>[t,500*(target-t)])}));
 return {notes,motion:{samples:times.map(time=>({time,chunk:0})),coordinate_registration:{chunks:[{chunk:0,status:'fitted',head_offsets:notes.map((n,i)=>({note:i,offset_pixels:500*n.target_seconds}))}]}}};
}
export function apply(data:RecordData,origin=0,reference:RecordData={},rows=32):RecordData{
 return beatView({schema:1,data,reference:{status:'available',song_start_seconds:origin,alignment_uncertainty_seconds:0,...reference},
  timing_text:':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'.repeat(rows)});
}
export function resize(data:RecordData,scale:number):RecordData{
 const d=structuredClone(data);
 for(const key of['analysis_width','analysis_height'])if(Object.hasOwn(d,key))d[key]*=scale;
 for(const n of d.notes){n.points=n.points.map(([t,y])=>[t,y*scale]);if(n.motion_clock)for(const key of['velocity','intercept'])n.motion_clock[key]*=scale;if(Object.hasOwn(n,'motion_target_phase'))n.motion_target_phase*=scale;}
 for(const r of d.head_registration.notes)if(Object.hasOwn(r,'coordinate_uncertainty_pixels'))r.coordinate_uncertainty_pixels*=scale;
 for(const s of d.scroll_motion?.samples??[])s.phase*=scale;
 for(const c of d.scroll_motion?.coordinate_registration?.chunks??[])for(const h of c.head_offsets)h.offset_pixels*=scale;
 return JSON.parse(JSON.stringify(d));
}
export function recovery(failed=[4]):RecordData{
 const d=domain();d.notes.forEach((n,i)=>{n.prediction_uncertainty_seconds=.001;n.beat_reconstruction={status:'restored'};
 if(!failed.includes(i))return;Object.assign(n,{status:'excluded',reason:'shared_timing_reconstruction_failed',target_seconds:null,
  timing_reconstruction:{status:'failed',reason:'insufficient_or_inconsistent_shared_motion',unaccepted_previous_estimate:{target_seconds:n.target_seconds-.02}}});delete n.motion_clock;delete n.motion_target_phase;});
 d.timing_reconstruction={status:'failed',failed_notes:failed.length,restored_notes:9-failed.length,warnings:failed.map(note=>({note,reason:'shared_timing_reconstruction_failed'}))};return d;
}
export function rejected():[RecordData,RecordData[]]{
 const d=coordinates(),groups=[];for(const ids of [[3,4,5],[0,1,2],[6,7,8]]){
 groups.push({notes:ids,unconstrained_row_domains:ids.map(i=>[8+i,8+i])});for(const i of ids){const n=d.notes[i];Object.assign(n,{beat_reconstruction:{status:'restored',group_index:groups.length-1},video_target_range:[n.target_seconds-.001,n.target_seconds+.001]});}}
 Object.assign(d.notes[4],{status:'excluded',reason:'beat_timing_reconstruction_failed',target_seconds:null,video_target_range:[1.519,1.522],
  timing_reconstruction:{status:'restored',method:'source_clock'},beat_reconstruction:{status:'failed',reason:'native_coordinate_domains_incompatible',group_index:0}});return [d,groups];
}
export function sparse():[RecordData,RecordData[]]{
 const d=recovery(),targets=[3,3.125,3.25,3.375,4.5,5.5,5.625,5.75,5.875];d.analysis_height=1600;d.layout.receptor_y=40/1600;
 targets.forEach((target,i)=>{const n=d.notes[i];n.points=n.points.map(([t])=>[t,40+240*(target-t)]);d.scroll_motion.coordinate_registration.chunks[0].head_offsets[i].offset_pixels=40+240*target;
  Object.assign(n,{beat_reconstruction:{status:'restored',group_index:0},video_target_range:[target-.001,target+.001]});
  if(i===4)n.timing_reconstruction.unaccepted_previous_estimate.target_seconds=4.48;else n.target_seconds=target;});
 return [d,[{notes:targets.map((_,i)=>i),unconstrained_row_domains:targets.map(t=>[Math.round(t*8),Math.round(t*8)])}]];
}
