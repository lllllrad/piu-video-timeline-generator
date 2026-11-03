/** Source-bound timing intervals when a common displacement clock is unavailable. */
import {contracts} from './contracts.ts';
import {clipPlane,type Vertex} from './coordinates/polygon.ts';
import {lowerBound} from './math.ts';
import type {RecordData} from './types.ts';
const F=contracts.native_clock;

function futureCompatible(samples:RecordData[],last:number,end:number,velocity:number[],capture:number):boolean{
 let previous=null,start=null,lo=0,hi=0;
 for(const s of samples.filter(s=>last<=s.time&&s.time<=end)){
  const interval=s.native_displacement_interval?.range_pixels;
  if(!previous||s.chunk!==previous.chunk||s.time-previous.time>F.maximum_capture_gap_seconds||!interval){start=s;lo=hi=0;}
  else{
   lo+=interval[0];hi+=interval[1];const dt=s.time-start.time;
   if(dt>=F.maximum_capture_gap_seconds&&
    (hi<velocity[0]*Math.max(0,dt-2*capture)-1e-8||lo>velocity[1]*(dt+2*capture)+1e-8))return false;
  }
  previous=s;
 }
 return true;
}

export function fit(state:RecordData,track:RecordData,receptor:number,layout:RecordData):RecordData|null{
 const error=track.registration_uncertainty_pixels,spacing=state.spacing;
 if(track.coordinate_basis!=='native_cap_center'||!Number.isFinite(error)||error<=0||!state.samples?.length)return null;
 if((state.coordinate_conflicts??[]).some(w=>w.note===track.note_index||w.peer_notes?.includes(track.note_index)))return null;
 const samples:RecordData[]=state.samples,times=samples.map(s=>s.time),at=new Map<number,RecordData>(samples.map(s=>[s.time,s])),bottom=(layout.note_y_max??.95)*state.height;
 const visible=track.points.filter(([t,y])=>receptor+.85*spacing<y&&y<bottom-.55*spacing);
 let start=0;for(let i=1;i<visible.length;i++)if(visible[i][0]-visible[i-1][0]>F.maximum_capture_gap_seconds+1e-6)start=i;
 const points=visible.slice(start);
 if(points.length<F.minimum_frames||points.at(-1)[0]-points[0][0]<F.minimum_span_seconds||
  points[0][1]-points.at(-1)[1]<F.minimum_displacement_spacing*spacing)return null;
 if(points.some(([t,y])=>!Number.isFinite(t)||!Number.isFinite(y)||!Number.isFinite(at.get(t)?.source_pts)||
  state.coordinate_failures?.[at.get(t)?.chunk]==='joint_coordinates_contradict_forward_motion'))return null;
 const observations=points.map(([time,y])=>{
  const i=lowerBound(times,time),steps=[i>0?time-times[i-1]:NaN,i+1<times.length?times[i+1]-time:NaN].filter(v=>Number.isFinite(v)&&v>0),half=Math.max(...steps)/2;
  return {time,source_pts_seconds:at.get(time).source_pts,y_pixels:y,coordinate_uncertainty_pixels:error,capture_range_seconds:[time-half,time+half]};
 });
 if(observations.some(o=>!Number.isFinite(o.capture_range_seconds[0])||o.capture_range_seconds[1]-o.capture_range_seconds[0]>F.maximum_capture_gap_seconds+1e-6))return null;
 if(new Set(observations.map(o=>o.source_pts_seconds)).size!==observations.length)return null;
 let plateau=0;
 for(let i=0;i<observations.length;){
  let j=i+1;while(j<observations.length&&Math.abs(observations[j].y_pixels-observations[i].y_pixels)<1e-8)j++;
  const span=observations[j-1].time-observations[i].time;plateau=Math.max(plateau,span);
  const range=[observations[i].capture_range_seconds[0],observations[j-1].capture_range_seconds[1]];
  for(let k=i;k<j;k++)observations[k].capture_range_seconds=[...range];i=j;
 }
 if(plateau>F.maximum_capture_gap_seconds+1e-6)return null;
 const last=points.at(-1),origin=last[0],maximumVelocity=F.maximum_speed_spacing_per_second*spacing,
  capture=Math.max(...observations.map(o=>Math.max(o.time-o.capture_range_seconds[0],o.capture_range_seconds[1]-o.time))),radius=error+maximumVelocity*capture;
 let vertices:Vertex[]=[[spacing,last[1]-radius],[maximumVelocity,last[1]-radius],[maximumVelocity,last[1]+radius],[spacing,last[1]+radius]];
 for(const o of observations){
  vertices=clipPlane(vertices,([v,b])=>b-v*(o.capture_range_seconds[0]-origin)-(o.y_pixels-error));
  vertices=clipPlane(vertices,([v,b])=>o.y_pixels+error-b+v*(o.capture_range_seconds[1]-origin));
  if(!vertices.length)return null;
 }
 const crossings=vertices.map(([v,b])=>origin+(b-receptor)/v),range=[Math.min(...crossings),Math.max(...crossings)],
  velocity=[Math.min(...vertices.map(p=>p[0])),Math.max(...vertices.map(p=>p[0]))];
 if(range[0]<origin-capture||range[1]-origin>F.maximum_extrapolation_seconds||range[0]<times[0]||range[1]>times.at(-1))return null;
 const a=Math.max(0,lowerBound(times,origin)-1),b=lowerBound(times,range[1]);
 if(samples.slice(a,b+1).slice(1).some((s,i)=>s.time-samples[a+i].time>F.maximum_capture_gap_seconds+1e-6))return null;
 if(!futureCompatible(samples,origin,range[1],velocity,capture))return null;
 const representative=vertices.reduce((sum,p)=>[sum[0]+p[0]/vertices.length,sum[1]+p[1]/vertices.length],[0,0]),
  target=origin+(representative[1]-receptor)/representative[0],first=Math.max(0,lowerBound(times,range[0])-1),after=lowerBound(times,range[1]);
 return {status:'estimated',reason:null,target_seconds:target,prediction_uncertainty_seconds:Math.max(target-range[0],range[1]-target),
  velocity_pixels_per_second:-representative[0],motion_clock:null,fit_method:'source_bound_native_interval',
  native_interval_model:{format:F,origin_seconds:origin,vertices,representative,target_range_seconds:range,observations},
  crossing_frame_seconds:[times[first],times[after]],crossing_source_pts_seconds:[samples[first].source_pts,samples[after].source_pts],crossing_capture_range:range,
  native_clock_warning:{reason:'shared_subframe_clock_unresolved',interpretation:'source_bound_native_interval_without_common_clock',
   source_pts_seconds:observations.map(o=>o.source_pts_seconds),capture_plateau_seconds:plateau}};
}

export function fitMany(state:RecordData,tracks:RecordData[],receptor:number,layout:RecordData):RecordData[]{
 return tracks.map(t=>fit(state,t,receptor,layout));
}
