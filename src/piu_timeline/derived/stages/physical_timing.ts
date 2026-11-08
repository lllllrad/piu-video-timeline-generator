/** Coordinates -> physical crossing intervals. No musical reference or input channel. */
import {registered,fitTrack} from '../tracks.ts';
import {fitMany as sharedClocks} from '../clocks.ts';
import {fitMany as nativeClocks} from '../native_clock.ts';
import {spacingFailures} from '../beats/spacing.ts';
import {summarize} from '../timing_summary.ts';
import {contracts} from '../contracts.ts';
import {Store,implementation,atomicJSON} from '../pipeline/store.ts';
import {resolve as resolvePath} from 'node:path';
import {median} from '../math.ts';
import {materialize as coordinateView} from './coordinates.ts';
import {boundArtifact,requireArtifact,requireInput,physicalFields,type CoordinateSource,type TimingSource} from './contracts.ts';
import type {RecordData} from '../types.ts';
const inputOf=(source:CoordinateSource):CoordinateSource=>({observations:source.observations,coordinates:source.coordinates});
const pick=(value:RecordData,fields:readonly string[])=>Object.fromEntries(fields.filter(k=>Object.hasOwn(value,k)).map(k=>[k,value[k]]));

/** Capture a completed numerical result, independently of adapters and association state. */
export function capture(source:CoordinateSource,result:RecordData):TimingSource{
 const base=coordinateView(source);
 if(result.notes.length!==base.notes.length||result.notes.some((n,i)=>n.lane!==base.notes[i].lane))throw Error('Physical timing changed observation identities');
 const physical_timing=boundArtifact('physical-timing',inputOf(source),{
  notes:result.notes.map((n,note)=>({note,values:pick(n,physicalFields)})),
  ...pick(result,['scroll_motion','timing_reconstruction'])},source.coordinates.artifact_root);
 return {...inputOf(source),physical_timing};
}
export function materialize(source:TimingSource):RecordData{
 const result=source.physical_timing;
 requireArtifact(result,'physical-timing');requireInput(result,inputOf(source));const base=coordinateView(source);
 if(Object.keys(result.data).some(k=>!['notes','scroll_motion','timing_reconstruction'].includes(k))||
  result.data.notes.length!==base.notes.length||result.data.notes.some((n,i)=>n.note!==i||Object.keys(n.values).some(k=>!(physicalFields as readonly string[]).includes(k))))throw Error('Foreign physical timing fields or identities');
 return {...base,...structuredClone(result.data),notes:base.notes.map((n,i)=>({...n,...structuredClone(result.data.notes[i].values)}))};
}

/** All per-track kernels execute in one runtime call; source frames stay unchanged. */
export function reconstruct(source:CoordinateSource):TimingSource{
 return capture(source,solve(coordinateView(source)));
}

export function solve(data:RecordData,suppliedTracks?:RecordData[]):RecordData{
 const height=data.analysis_height,width=data.analysis_width,layout=data.layout;
 if(!Number.isFinite(height)||!Number.isFinite(width)||!layout?.lanes?.length||!data.frame_timeline.length)throw Error('Physical timing requires geometry and source timeline');
 const timeline=data.frame_timeline;
 if(timeline.some((s,i)=>![s.time,s.source_pts].every(Number.isFinite)||i>0&&(s.time<=timeline[i-1].time||s.source_pts<=timeline[i-1].source_pts)))throw Error('Physical source timeline must increase');
 const spacing=median(layout.lanes.slice(1).map((l,i)=>(l.x-layout.lanes[i].x)*width)),receptor=layout.receptor_y*height;
 const registrations=new Map<number,RecordData>((data.head_registration?.notes??[]).map(r=>[r.note,r]));
 const tracks:RecordData[]=suppliedTracks??data.notes.map((note,note_index)=>{
  const r=registrations.get(note_index),times=new Set(note.points.map(([t])=>t)),observations=(r?.observations??[]).filter(o=>times.has(o.time)),qualified=observations.filter(o=>'native_cap_projection_uncertainty_pixels'in o);
  return {note_index,lane:note.lane,points:note.points,
   registration_uncertainty_pixels:qualified.length?Math.max(...qualified.map(o=>o.native_cap_coordinate_uncertainty_pixels??o.native_cap_projection_uncertainty_pixels)):r?.coordinate_uncertainty_pixels??0,
   coordinate_basis:r?.coordinate_method==='native_image_anchors'&&observations.length&&observations.every(o=>'native_cap_coordinate_uncertainty_pixels'in o)?'native_cap_center':null};
 });
 const result=registered(tracks,data.frame_timeline,height,spacing,receptor,(layout.note_y_max??.95)*height);
 const state={...result,height,spacing,strict_clock:true};
 tracks.forEach((t,i)=>{t['registration_offsets']=Object.fromEntries(result.coordinate_offsets.filter(([n])=>n===i).map(([,chunk,value])=>[chunk,value]));});
 const fitted=sharedClocks(state,tracks,receptor,layout),pending=tracks.filter((_,i)=>!fitted[i]);
 const bounded=nativeClocks(state,pending,receptor,layout),native=new Map(pending.map((t,i)=>[t.note_index,bounded[i]]));
 const notes=data.notes.map((n,i)=>({...n,...fitTrack(tracks[i],receptor,spacing)}));
 const frames=new Map<number,Map<number,number>>();
 tracks.forEach((t,i)=>t.points.forEach(([time,y])=>{if(!frames.has(time))frames.set(time,new Map());frames.get(time).set(i,y);}));
 const at=new Map<number,RecordData>(result.samples.map(s=>[s.time,s])),warnings=[...result.coordinate_conflicts];
 notes.forEach((note,index)=>{
  const track=tracks[index],points=track.points;let fit=fitted[index]??native.get(index);
  if((points.length<4||points.at(-1)[0]-points[0][0]<.065)&&!fit?.native_motion_support)return;
  const peers=new Map<number,number>();
  for(const [time,y]of points)for(const [peer,py]of frames.get(time))if(peer!==index&&(tracks[peer].lane!==track.lane||Math.abs(py-y)>.65*spacing))peers.set(peer,(peers.get(peer)??0)+1);
  if(![...peers.values()].some(n=>n>=4)&&!fit&&track.coordinate_basis!=='native_cap_center'){
   const direct=fitTrack(track,receptor,spacing);if(direct.status==='estimated')fit={...direct,fit_method:'isolated_native_track'};
  }
  const previous=pick(note,['target_seconds','prediction_uncertainty_seconds','fit_method','native_clock_warning','crossing_method']);
  for(const key of ['native_clock_warning','crossing_method','native_interval_model','native_motion_support','motion_clock_validation'])if(!fit||!Object.hasOwn(fit,key))delete note[key];
  if(!fit){
   const visible=points.filter(([,y])=>receptor+.85*spacing<y&&y<(layout.note_y_max??.95)*height-.55*spacing).map(([t])=>at.get(t));
   const reason=(visible.length?result.coordinate_failures[visible.at(-1).chunk]:null)??'insufficient_or_inconsistent_shared_motion';
   Object.assign(note,{status:'excluded',reason:'shared_timing_reconstruction_failed',target_seconds:null,timing_reconstruction:{status:'failed',reason,unaccepted_previous_estimate:previous}});
   warnings.push({note:index,lane:track.lane,reason:'shared_timing_reconstruction_failed',check:'timing_reconstruction',visible_start_seconds:points[0][0],visible_end_seconds:points.at(-1)[0],observed_points:points.length,failure_detail:reason});
  }else{
   if(fit.native_interval_model)for(const key of ['motion_target_phase','clock_target_phase','motion_chunk','motion_support_points','coordinate_bridge'])delete note[key];
   Object.assign(note,fit,{timing_reconstruction:{status:'restored',format:contracts.shared_motion}});
   if(fit.native_clock_warning)warnings.push({note:index,lane:track.lane,check:'timing_reconstruction',...fit.native_clock_warning,visible_start_seconds:fit.crossing_capture_range[0],visible_end_seconds:fit.crossing_capture_range[1],crossing_source_pts_seconds:fit.crossing_source_pts_seconds});
  }
 });
 const motion={format:contracts.shared_motion,samples:result.samples,coordinate_registration:result.coordinate_registration,
  supported_steps:result.samples.filter(s=>s.support>0).length,total_steps:Math.max(0,result.samples.length-1)};
 const kept:number[]=[];
 for(const i of notes.map((_,i)=>i).sort((a,b)=>(notes[a].prediction_uncertainty_seconds??Infinity)-(notes[b].prediction_uncertainty_seconds??Infinity)||notes[b].points.length-notes[a].points.length)){
  const note=notes[i];if(note.status!=='estimated')continue;
  const owner=kept.find(j=>{if(notes[j].lane!==note.lane||Math.abs(notes[j].target_seconds-note.target_seconds)>=.035)return false;
   const at=new Map<number,number>(notes[j].points),errors=note.points.filter(([t])=>at.has(t)).map(([t,y])=>Math.abs(y-at.get(t)));
   return errors.length>=4&&errors.filter(e=>e<=2).length>=.8*errors.length;});
  if(owner!==undefined)Object.assign(note,{status:'excluded',reason:'duplicate_head_component',duplicate_of:owner});else kept.push(i);
 }
 const conflicts=spacingFailures(notes,spacing,motion);warnings.push(...conflicts);
 for(const conflict of conflicts){const note=notes[conflict.note],previous=pick(note,['target_seconds','prediction_uncertainty_seconds','fit_method']);
  Object.assign(note,{status:'excluded',reason:conflict.reason,target_seconds:null,timing_reconstruction:{status:'failed',reason:conflict.reason,unaccepted_previous_estimate:previous}});}
 return {notes,scroll_motion:motion,motion_state:result,timing_reconstruction:{format:contracts.shared_motion,...summarize(notes,warnings)}};
}

/** Reuse only the declared coordinate input and complete implementation dependency graph. */
export function saved(source:CoordinateSource,directory:string):TimingSource{
 const store=new Store(directory),physical_timing=store.run('physical-timing',implementation(new URL('./physical_timing.ts',import.meta.url)),source,()=>reconstruct(source).physical_timing);
 const result={...inputOf(source),physical_timing};materialize(result);
 atomicJSON(resolvePath(directory,'physical-timing.json'),physical_timing);
 return result;
}
