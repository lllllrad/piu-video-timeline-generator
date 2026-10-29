/** Corroborate a missing cap region with independent native appearance pixels. */
import {contracts} from './contracts.ts';
import {equal,median} from './math.ts';
import type {RecordData} from './types.ts';
const F=contracts.cap_coverage;

export function accountCapCoverage(data:RecordData):RecordData{
 const channel=data.visual_channels?.processing,analysis=data.hold_analysis;
 if(!analysis||!equal(channel?.format?.cap_coverage,F))return data;
 const timeline=new Map<number,number>(data.visual_channels?.timeline?.frames??[]);
 const tracked=new Map<number,Set<number>>((data.notes??[]).map((n,i)=>[i,new Set<number>((n.points??[]).map(([t])=>timeline.get(t)).filter(Number.isFinite))]));
 const pixels=channel.pixel_coordinates,layout=data.layout;
 if(!pixels||!(pixels.width>0&&pixels.height>0)||!(data.analysis_height>0)||!Array.isArray(layout?.lanes)||layout.lanes.length<2)return data;
 const spacing=median(layout.lanes.slice(1).map((l,i)=>(l.x-layout.lanes[i].x)*pixels.width));
 const heightLimit=(2*Math.max(2,Math.floor(F.radius_spacing*spacing+.5+1e-9))+1)*data.analysis_height/pixels.height;
 const records=new Map<number,RecordData>((channel.notes??[]).map(r=>[r.note,r]));
 const qualified=(note:number,time:number,pts:number):RecordData[]=>{
  const r=records.get(note);if(r?.status!=='hold_component')return [];
  const candidates=(r.cap_coverage??[]).filter(p=>p.playback_seconds===time);
  if(candidates.length!==1)return [];
  const p=candidates[0],ref=p.reference??{},references=ref.supporting_source_pts_seconds??[],range=ref.observed_y_range_pixels;
  if(!Number.isFinite(time)||!Number.isFinite(pts)||timeline.get(time)!==pts||p.source_pts_seconds!==pts||!Number.isFinite(p.score)||p.score<F.minimum_similarity||
   !Number.isInteger(p.template_pose)||!Array.isArray(references)||new Set(references).size<F.minimum_reference_frames||
   !references.includes(ref.source_pts_seconds)||references.some(t=>!Number.isFinite(t)||!tracked.get(note)?.has(t))||
   !Array.isArray(range)||range.length!==2||range.some(v=>!Number.isFinite(v))||
   !(p.native_lane_spacing_pixels>0)||Math.abs(p.native_lane_spacing_pixels-spacing)>1e-6||range[1]-range[0]<F.minimum_displacement_spacing*p.native_lane_spacing_pixels||
   !Array.isArray(p.box_pixels)||p.box_pixels.length!==2||p.box_pixels.some(v=>!Number.isFinite(v))||p.box_pixels[0]>=p.box_pixels[1]||p.box_pixels[0]<0||p.box_pixels[1]>data.analysis_height||p.box_pixels[1]-p.box_pixels[0]>heightLimit+1e-6||
   !Array.isArray(p.intervals_pixels)||p.intervals_pixels.some(b=>b.length!==2||b.some(v=>!Number.isFinite(v))||b[0]>=b[1]||b[0]<p.box_pixels[0]||b[1]>p.box_pixels[1]))return [];
  return [{note,...p}];
 };
 const unresolved=[],accounted=[...(analysis.accounted_cap_coverage??[])];
 for(const warning of analysis.unresolved_tracks??[]){
  const hold=(analysis.holds??[]).find(h=>h.image_connection_id===warning.image_connection_id&&h.head_note===warning.note&&h.tail_note===warning.tail_note&&h.lane===warning.lane);
  if(warning.failure_detail!=='known_hold_image_connection_not_observed_in_clear_frames'||!hold||!Number.isInteger(warning.image_connection_id)||!(hold.body_frames>=4)||!warning.image_evidence?.length){unresolved.push(warning);continue;}
  const remaining=[],proofs=[];
  for(const e of warning.image_evidence){
   if(!Array.isArray(e.missing_intervals_pixels)||!e.missing_intervals_pixels.length||e.missing_intervals_pixels.some(b=>!Array.isArray(b)||b.length!==2||b.some(v=>!Number.isFinite(v))||b[0]>=b[1])){remaining.push(e);continue;}
   const caps=[hold.head_note,hold.tail_note].flatMap(n=>qualified(n,e.time,e.source_pts));
   const spans=caps.flatMap(p=>p.intervals_pixels).sort((a,b)=>a[0]-b[0]);
   const gaps=[];
   for(const [lo,hi]of e.missing_intervals_pixels){
    let cursor=lo;
    for(const[a,b]of spans){if(b<=cursor)continue;if(a>=hi)break;if(a>cursor)gaps.push([cursor,Math.min(a,hi)]);cursor=Math.max(cursor,b);if(cursor>=hi)break;}
    if(cursor<hi)gaps.push([cursor,hi]);
   }
   if(equal(gaps,e.missing_intervals_pixels)){remaining.push(e);continue;}
   proofs.push({time:e.time,source_pts_seconds:e.source_pts,original_missing_intervals_pixels:e.missing_intervals_pixels,remaining_intervals_pixels:gaps,cap_measurements:caps});
   if(gaps.length)remaining.push({...e,missing_intervals_pixels:gaps});
  }
  if(proofs.length)accounted.push({native_warning:warning,measurements:proofs,status:remaining.length?'partially_corroborated':'corroborated'});
  if(remaining.length)unresolved.push({...warning,image_evidence:remaining,visible_start_seconds:Math.min(...remaining.map(e=>e.time)),visible_end_seconds:Math.max(...remaining.map(e=>e.time)),observed_points:new Set(remaining.map(e=>e.time)).size});
 }
 return {...data,hold_analysis:{...analysis,unresolved_tracks:unresolved,accounted_cap_coverage:accounted}};
}
