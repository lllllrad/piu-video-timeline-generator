/** Source-only local motion bounds for deferred identities, never target or input timing. */
import {contracts}from '../contracts.ts';
import {roundoff,lowerBound,upperBound}from '../math.ts';
import type {RecordData}from '../types.ts';
export type IdentityDecision={status:'supported'|'refuted'|'pending';reason:string;proof?:RecordData};
type State=IdentityDecision;
/** A capture-phase allowance is v * source period, never a coordinate radius. */
function velocityDomain(observations:RecordData[],period:number,limit:number):number[]|null{
 if(observations.some(o=>!o.center))return null;
 let lo=0,hi=limit;
 for(const a of observations)for(const b of observations){
  const coefficient=b.time-a.time+2*period,
   delta=a.center.yPixels-b.center.yPixels-a.center.uncertaintyPixels-b.center.uncertaintyPixels;
  if(coefficient>0)lo=Math.max(lo,delta/coefficient);
  else if(coefficient<0)hi=Math.min(hi,delta/coefficient);
  else if(delta>roundoff(a.center.yPixels,b.center.yPixels))return null;
 }
 return lo<=hi?[lo,hi]:null;
}

export function referenceMotion(source:RecordData[],timeline:RecordData[],spacing:number){
 const at=new Map<number,RecordData[]>(),limit=contracts.frame_tracking.maximum_speed_spacing_per_second*spacing;
 const times=timeline.map(s=>s.time);
 const stamps=new Map(timeline.map(s=>[s.time,s.source_pts]));
 const cadence=timeline.length>1?(times.at(-1)-times[0])/(times.length-1):1/60,
  count=Math.max(12,Math.ceil(contracts.frame_tracking.identity_history_seconds/cadence)+4);
 for(const track of source){
  const observations=track.observations;
  if(observations.length<4||observations.some(o=>!o.center||!Number.isFinite(o.sourcePtsSeconds)||stamps.get(o.time)!==o.sourcePtsSeconds)||
   observations.slice(1).some((o,i)=>o.time<=observations[i].time||o.sourcePtsSeconds<=observations[i].sourcePtsSeconds||
    Math.abs((o.time-observations[i].time)-(o.sourcePtsSeconds-observations[i].sourcePtsSeconds))>1e-6))continue;
  for(let start=0;start<observations.length-3;start+=4){
   const window=observations.slice(start,start+count),first=window[0].time,last=window.at(-1).time;
   if(last-first<.065||window.slice(1).some((o,i)=>o.time-window[i].time>.05+1e-6))continue;
   const frames=timeline.slice(lowerBound(times,first),upperBound(times,last));
   if(frames.length<4||frames.some(s=>!Number.isFinite(s.source_pts)))continue;
   const period=Math.max(...frames.slice(1).map((s,i)=>Math.max(s.time-frames[i].time,s.source_pts-frames[i].source_pts)));
   if(!(period>0&&period<=.05+1e-6))continue;
   const domain=velocityDomain(window,period,limit);if(!domain)continue;
   const model={fragment:track.id,lane:track.lane,window:[first,last],period,velocity_range:domain,
    source_pts_seconds:window.map(o=>o.sourcePtsSeconds),observations:window.map(o=>({time:o.time,y_pixels:o.center.yPixels,uncertainty_pixels:o.center.uncertaintyPixels}))};
   for(let key=Math.floor(first/.05);key<=Math.floor(last/.05);key++){
    if(!at.has(key))at.set(key,[]);at.get(key).push(model);
   }
  }
 }
 return (a:RecordData,b:RecordData):State=>{
  const from=a.observations.at(-1),to=b.observations[0],own=[...a.observations.slice(-12),...b.observations.slice(0,12)];
  if(!from||!to||own.some(o=>!o.center||!Number.isFinite(o.sourcePtsSeconds)))return {status:'pending',reason:'missing_source_bound_center'};
  if(own.slice(1).some((o,i)=>o.time<=own[i].time||o.sourcePtsSeconds<=own[i].sourcePtsSeconds||
   Math.abs((o.time-own[i].time)-(o.sourcePtsSeconds-own[i].sourcePtsSeconds))>1e-6))
   return {status:'pending',reason:'discontinuous_source_identity'};
  const covering=(at.get(Math.floor(from.time/.05))??[]).filter(r=>r.window[0]<=from.time&&to.time<=r.window[1]);
  for(const ref of covering.filter(r=>r.lane===a.lane)){
   const positions=new Map(ref.observations.map(o=>[o.time,o]));
   const signs=(list:RecordData[])=>list.flatMap(o=>{
    const other=positions.get(o.time)as RecordData|undefined;if(!other)return [];
    const delta=o.center.yPixels-other.y_pixels,error=o.center.uncertaintyPixels+other.uncertainty_pixels;
    return Math.abs(delta)>error+roundoff(o.center.yPixels,other.y_pixels)?[Math.sign(delta)]:[];
   });
   const before=signs(a.observations.slice(-12)),after=signs(b.observations.slice(0,12));
   if(before.length>=2&&after.length>=2&&new Set(before).size===1&&new Set(after).size===1&&before[0]!==after[0])
    return {status:'refuted',reason:'contradicts_coobserved_native_order'};
  }
  const refs=covering.filter(r=>r.lane!==a.lane);
  if(new Set(refs.map(r=>r.lane)).size<2)return {status:'pending',reason:'independent_motion_references_unavailable'};
  const lower=Math.max(...refs.map(r=>r.velocity_range[0])),upper=Math.min(...refs.map(r=>r.velocity_range[1]));
  if(lower>upper)return {status:'pending',reason:'independent_motion_references_conflict'};
  const window=[Math.max(...refs.map(r=>r.window[0])),Math.min(...refs.map(r=>r.window[1]))],
   captured=own.filter(o=>window[0]<=o.time&&o.time<=window[1]),
   period=Math.max(...refs.map(r=>r.period)),domain=velocityDomain(captured,period,limit);
  if(!domain||Math.max(lower,domain[0])>Math.min(upper,domain[1]))return {status:'refuted',reason:'contradicts_independent_native_motion'};
  return {status:'supported',reason:'independent_past_and_future_native_motion',proof:{
   method:'deferred_independent_native_clock',predecessor_end_seconds:from.time,successor_start_seconds:to.time,
   source_capture_period_seconds:period,velocity_range_pixels_per_second:[Math.max(lower,domain[0]),Math.min(upper,domain[1])],
   references:refs.map(({period,velocity_range,...ref})=>({...ref,source_capture_period_seconds:period,velocity_range_pixels_per_second:velocity_range})),
   source_pts_seconds:captured.map(o=>o.sourcePtsSeconds),endpoint_uncertainty_pixels:Math.max(...captured.map(o=>o.center.uncertaintyPixels))}};
 };
}
