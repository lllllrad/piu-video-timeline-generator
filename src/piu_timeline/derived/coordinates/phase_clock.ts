/** Feasible constant-speed clocks for one retained, registered render-phase block. */
import {contracts}from '../contracts.ts';
import {clipAffine as clip,type Vertex}from './polygon.ts';
import type {RecordData}from '../types.ts';
const F=contracts.render_clock;

export function fit(motion:RecordData|null,endpointError:number):RecordData[]{
 if(!motion||!Number.isFinite(endpointError)||endpointError<=0)return [];
 const records=new Map((motion.coordinate_registration?.chunks??[]).filter(r=>r.status==='fitted').map(r=>[r.chunk,r])),
  chunks=new Map<number,RecordData[]>();
 for(const s of motion.samples??[]){if(!chunks.has(s.chunk))chunks.set(s.chunk,[]);chunks.get(s.chunk).push(s);}
 const result=[];
 for(const [chunk,samples]of chunks){
  if(!records.has(chunk)||samples.length<4)continue;
  if(samples.some(s=>![s.time,s.source_pts,s.phase].every(Number.isFinite)))continue;
  const first=samples[0],last=samples.at(-1),span=last.time-first.time;
  if(span<F.minimum_span_seconds||samples.slice(1).some((s,i)=>s.time<=samples[i].time||
   s.time-samples[i].time>F.maximum_capture_gap_seconds+1e-6||s.source_pts<=samples[i].source_pts||
   s.phase<samples[i].phase-1e-8||!(s.support>0)))continue;
  const declared=samples.flatMap(s=>s.native_displacement_interval?.endpoint_intervals_pixels??[]);
  if(declared.some(r=>!Array.isArray(r)||r.length!==2||!r.every(Number.isFinite)||r[0]>r[1]))continue;
  const phaseEndpointError=Math.max(endpointError,...declared.map(r=>(r[1]-r[0])/4)),
   capture=Math.max(...samples.slice(1).map((s,i)=>s.phase-samples[i].phase)),
   error=capture+F.endpoint_error_multiplier*phaseEndpointError,travel=last.phase-first.phase;
  if(!(capture>0&&travel>2*error))continue;
  const lo=Math.max(0,(travel-2*error)/span),hi=(travel+2*error)/span;
  let vertices:Vertex[]=[[lo,first.phase-error],[hi,first.phase-error],[hi,first.phase+error],[lo,first.phase+error]];
  for(const s of samples){vertices=clip(vertices,s.time-first.time,s.phase,error);if(!vertices.length)break;}
  if(!vertices.length||vertices.some(([v])=>v<=0))continue;
  result.push({format:F,chunk,window:[first.time,last.time],origin_seconds:first.time,vertices,
   velocity_range_pixels_per_second:[Math.min(...vertices.map(p=>p[0])),Math.max(...vertices.map(p=>p[0]))],
   phase_error_pixels:error,observed_render_step_pixels:capture,endpoint_uncertainty_pixels:endpointError,phase_endpoint_uncertainty_pixels:phaseEndpointError,
   source_pts_range:[first.source_pts,last.source_pts],frames:samples.length,
   head_notes:((records.get(chunk)as RecordData).head_offsets??[]).map(h=>h.note)});
 }
 return result;
}

export function covering(models:RecordData[],ids:number[],notes:RecordData[],samples:RecordData[]):RecordData|null{
 const eligible=models.filter(m=>ids.every(i=>m.head_notes.includes(i))&&notes.every(n=>
  Number.isFinite(n.target_seconds)&&Number.isFinite(n.prediction_uncertainty_seconds)&&n.prediction_uncertainty_seconds>=0&&
  m.window[0]<=n.target_seconds-n.prediction_uncertainty_seconds&&n.target_seconds+n.prediction_uncertainty_seconds<=m.window[1])&&(()=>{
   const times=samples.filter(s=>m.window[0]<=s.time&&s.time<=m.window[1]).map(s=>s.time);
   return times.length>=contracts.native_gap_validation.minimum_frames&&times.at(-1)-times[0]>=contracts.native_gap_validation.minimum_span_seconds;
  })());
 return eligible.length===1?eligible[0]:null;
}

/** Existing source estimates must agree with their own declared affine clock. */
export function sourceEstimate(note:RecordData):boolean{
 const c=note.motion_clock;if(!c)return true;
 const phase=note.clock_target_phase??note.motion_target_phase;
 if(![c.origin,c.intercept,c.velocity,c.residual,phase,note.target_seconds,note.prediction_uncertainty_seconds].every(Number.isFinite)||
  c.velocity<=0||c.residual<0||note.prediction_uncertainty_seconds<0||!Array.isArray(c.window)||c.window.length!==2||!c.window.every(Number.isFinite))return false;
 return Math.abs(c.origin+(phase-c.intercept)/c.velocity-note.target_seconds)<=1e-8&&
  note.target_seconds+note.prediction_uncertainty_seconds>=c.window[0]&&note.target_seconds-note.prediction_uncertainty_seconds<=c.window[1];
}

/** Crossing bounds retain every feasible source clock and the cap endpoint error. */
export function crossingRange(model:RecordData,phase:number,error:number):number[]|null{
 if(![phase,error].every(Number.isFinite)||error<0)return null;
 const values=model.vertices.flatMap(([v,b])=>[phase-error,phase+error].map(p=>model.origin_seconds+(p-b)/v)),
  range=[Math.min(...values),Math.max(...values)];
 return range.every(Number.isFinite)&&model.window[0]<=range[0]&&range[1]<=model.window[1]?range:null;
}
