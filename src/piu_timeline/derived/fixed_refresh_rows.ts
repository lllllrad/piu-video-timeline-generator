import {fitTrajectory} from './coordinates/points.ts';
/** Separate a physically corroborated fixed row from another refresh's candidates. */
import {contracts} from './contracts.ts';
import {bracket,onsetOverlaps,processingSupport,receptorEvidence} from './evidence.ts';
import {NativeGapMeasurements} from './native_gaps.ts';
import {median} from './math.ts';
import type {RecordData} from './types.ts';

function physicalEvidence(data:RecordData,match:RecordData,lo:number,hi:number,timeline:Map<number,RecordData>):RecordData|null{
 const lane=data.notes[match.note].lane,guard=2*(data.median_frame_interval_seconds||.017);
 const valid=(range,pts)=>Array.isArray(range)&&Array.isArray(pts)&&range.length===2&&pts.length===2&&
  range[0]<range[1]&&pts[0]<pts[1]&&range.every((t,i)=>Number.isFinite(pts[i])&&
   Number.isFinite(timeline.get(t)?.source_pts)&&Math.abs(timeline.get(t).source_pts-pts[i])<=1e-6);
 const runs=receptorEvidence(data).flatMap((r,i)=>r.lane===lane&&onsetOverlaps(r,lo,hi,guard)?[{r,i}]:[]);
 if(runs.length===1){
  const {r,i}=runs[0];
  const shared=(data.matches??[]).some(m=>m.note!==match.note&&data.notes[m.note].lane===lane&&
   bracket(m).every(Number.isFinite)&&onsetOverlaps(r,...bracket(m)as[number,number],guard));
  if(!shared&&valid(r.onset_range,r.onset_source_pts_seconds))return {kind:'exclusive_lane_onset',run:i,
   range:r.onset_range,source_pts_seconds:r.onset_source_pts_seconds};
 }
 const p=processingSupport(data,match.note,lo,hi,guard);
 if(p&&valid(p.range,p.source_pts_seconds))return {kind:'note_disappearance',note:match.note,range:p.range,source_pts_seconds:p.source_pts_seconds};
 return null;
}

export function fixedRefreshRow(data:RecordData,index:number,pending:number[],pairs:number[][],lo:number,hi:number):RecordData|null{
 const notes=data.notes??[],n=notes[index],m=(data.matches??[]).find(m=>m.note===index);
 if(!pending.length||!m||m.combo_event==null||m.judgment_event==null||m.processing_conflict||
  !Number.isFinite(m.target_seconds)||Math.abs(m.target_seconds-n.target_seconds)>1e-8||(m.aggregate_row_count??1)!==1||
  n.status!=='estimated'||n.type_status!=='tap'||n.note_type==='hold'||n.timing_reconstruction?.status!=='restored'||
  !pairs.some(([j,c])=>j===m.judgment_event&&c===m.combo_event))return null;
 const c=data.combo_events[m.combo_event],j=data.judgment_events[m.judgment_event];
 if(c.delta!==1||!['PERFECT','GREAT','GOOD','BAD'].includes(j.label)||j.detection_status==='excluded'||
  c.upper_seconds-c.lower_seconds>.1+1e-6||j.upper_seconds-j.lower_seconds>.05||
  j.anchor_combo_event!=null&&j.anchor_combo_event!==m.combo_event)return null;
 const a=Math.min(c.lower_seconds,j.lower_seconds),b=Math.max(c.upper_seconds,j.upper_seconds);
 if(!Number.isFinite(a)||!Number.isFinite(b)||!pending.every(i=>
  n.target_seconds>notes[i].target_seconds?a>hi:n.target_seconds<notes[i].target_seconds&&b<lo))return null;
 const timeline=new Map<number,RecordData>((data.scroll_motion?.samples??[]).map(s=>[s.time,s]));
 const physical=physicalEvidence(data,m,a,b,timeline);if(!physical)return null;
 const width=data.analysis_width,height=data.analysis_height,lanes=data.layout?.lanes;
 if(!Number.isFinite(width)||!Number.isFinite(height)||!Array.isArray(lanes)||lanes.length<2)return null;
 const spacing=median(lanes.slice(1).map((l,i)=>(l.x-lanes[i].x)*width));if(!(spacing>0))return null;
 const top=data.layout.receptor_y*height+.85*spacing,bottom=(data.layout.note_y_max??.95)*height-.55*spacing;
 const chunks=new Map<number,Set<number>>((data.scroll_motion?.coordinate_registration?.chunks??[])
  .filter(c=>c.status==='fitted').map(c=>[c.chunk,new Set<number>(c.head_offsets.map(h=>h.note))]));
 const fixed=new Map<number,number>(fitTrajectory(n).points),separation=[];
 for(const i of pending){
  const direction=Math.sign(n.target_seconds-notes[i].target_seconds);
  const samples=fitTrajectory(notes[i]).points.flatMap(([time,y])=>{
   const other=fixed.get(time),frame=timeline.get(time),heads=chunks.get(frame?.chunk);
   return other!=null&&top<y&&y<bottom&&top<other&&other<bottom&&heads?.has(i)&&heads.has(index)?
    [{time,source_pts_seconds:frame.source_pts,candidate_y_pixels:y,fixed_y_pixels:other,ordered_gap_pixels:direction*(other-y)}]:[];
  }).sort((a,b)=>a.time-b.time);
  if(samples.length<contracts.chords.minimum_frames||samples.at(-1).time-samples[0].time<contracts.chords.minimum_span_seconds||
   samples.some(s=>!Number.isFinite(s.source_pts_seconds))||
   samples.slice(1).some((s,k)=>!(0<s.time-samples[k].time&&s.time-samples[k].time<=.05+1e-6&&s.source_pts_seconds>samples[k].source_pts_seconds)))return null;
  const measured=new NativeGapMeasurements(data).compare({peer_notes:[i,index],reconstructed_gap_pixels:0,
   visible_start_seconds:samples[0].time,visible_end_seconds:samples.at(-1).time});
  const range=measured.allowed_gap_range_pixels;
  if(measured.reason!=='declared_native_endpoint_errors'||!range||range[0]>range[1]||
   !(direction>0?range[0]>0:range[1]<0))return null;
  separation.push({note:i,lane_spacing_pixels:spacing,
   position_error_pixels:Math.max(...measured.samples.map(s=>s.coordinate_uncertainties_pixels[0]+s.coordinate_uncertainties_pixels[1])),
   allowed_gap_range_pixels:range,coordinate_measurements:measured.samples,samples});
 }
 return {note:index,target_seconds:n.target_seconds,combo_event:m.combo_event,judgment_event:m.judgment_event,
  refresh_range:[a,b],physical_evidence:physical,native_row_separation:separation};
}
