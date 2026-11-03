/** Pairwise physical gaps constrain row differences before selecting a subdivision. */
import {contracts} from '../contracts.ts';
import {equal} from '../math.ts';
import {fitTrajectory} from '../coordinates/points.ts';
import {NativeGapMeasurements} from '../native_gaps.ts';
import type {Interval,RecordData} from '../types.ts';
const F=contracts.beat_gaps;

export function prepare(data:RecordData,groups:RecordData[]):RecordData[]{
 const membership=new Map<number,number>();groups.forEach((g,i)=>g.notes.forEach(n=>membership.set(n,i)));
 const at=new Map<number,number[]>(),pairs=new Map<string,number[]>(),measured=new NativeGapMeasurements(data);
 data.notes.forEach((n,i)=>{if(!membership.has(i))return;for(const [t]of fitTrajectory(n).points){if(!at.has(t))at.set(t,[]);at.get(t).push(i);}});
 for(const [time,notes]of at)for(let i=0;i<notes.length;i++)for(let j=i+1;j<notes.length;j++){
  const a=Math.min(notes[i],notes[j]),b=Math.max(notes[i],notes[j]);if(membership.get(a)!==membership.get(b))continue;
  const key=`${a},${b}`;if(!pairs.has(key))pairs.set(key,[]);pairs.get(key).push(time);
 }
 const proofs=[];
 for(const [key,times]of pairs){
  const ids=key.split(',').map(Number),notes=ids.map(i=>data.notes[i]),clock=notes[0].motion_clock;
  if(!clock||!equal(clock,notes[1].motion_clock)||!Array.isArray(clock.window)||clock.window.length!==2)continue;
  const span=clock.window[1]-clock.window[0];
  if(![clock.origin,clock.intercept,clock.velocity,clock.residual,...clock.window].every(Number.isFinite)||clock.velocity<=0||clock.residual<0||span<F.minimum_clock_span_seconds)continue;
  if(notes.some(n=>!Number.isFinite(n.clock_target_phase??n.motion_target_phase)||
   Math.abs(clock.origin+((n.clock_target_phase??n.motion_target_phase)-clock.intercept)/clock.velocity-n.target_seconds)>1e-8))continue;
  if(notes.some(n=>!Number.isFinite(n.target_seconds)||!Number.isFinite(n.prediction_uncertainty_seconds)||n.prediction_uncertainty_seconds<0||
   n.target_seconds-n.prediction_uncertainty_seconds<clock.window[0]||n.target_seconds+n.prediction_uncertainty_seconds>clock.window[1]))continue;
  const proof=measured.measure({peer_notes:ids,visible_start_seconds:Math.min(...times),visible_end_seconds:Math.max(...times)});
  if(proof.status!=='measured')continue;
  const endpointError=Math.max(...proof.samples.flatMap(s=>s.coordinate_uncertainties_pixels));
  const error=Math.max(F.slope_error_floor_pixels,F.slope_error_residual_multiplier*clock.residual,2*endpointError)/span;
  const velocity=[clock.velocity-error,clock.velocity+error];if(velocity[0]<=0)continue;
  const values=proof.allowed_gap_range_pixels.flatMap(g=>velocity.map(v=>g/v));
  proofs.push({peer_notes:ids,target_gap_range_seconds:[Math.min(...values),Math.max(...values)],
   source_velocity_range_pixels_per_second:velocity,source_clock:clock,native_gap_measurements:proof});
 }
 return proofs;
}

export function constrain(domains:Interval[],step:number,proofs:RecordData[]):[Interval[],RecordData[]]{
 const result=domains.map(d=>[...d]as Interval),used=[];
 const edges=proofs.filter(p=>p.indices.every(i=>domains[i][0]<=domains[i][1])).map(p=>{
  const [lo,hi]=p.target_gap_range_seconds;
  if(![lo,hi].every(Number.isFinite)||lo>hi)throw Error('Invalid measured beat gap');
  const row_delta_range=[Math.ceil(lo/step-1e-8),Math.floor(hi/step+1e-8)];
  const proof:RecordData={...p,row_delta_range};used.push(proof);return proof;
 });
 let changed=true;
 while(changed){
  changed=false;
  for(const p of edges){
   const [a,b]=p.indices,[lo,hi]=p.row_delta_range,first=result[a],second=result[b];
   let narrowed:Interval[];
   if(lo>hi||first[0]>first[1]||second[0]>second[1])narrowed=[[1,0],[1,0]];
   else narrowed=[[Math.max(first[0],second[0]-hi),Math.min(first[1],second[1]-lo)],
    [Math.max(second[0],first[0]+lo),Math.min(second[1],first[1]+hi)]];
   if(narrowed.some(([a,b])=>a>b))narrowed=[[1,0],[1,0]];
   if(!equal(narrowed,[first,second])){[result[a],result[b]]=narrowed;changed=true;}
  }
 }
 return [result,used];
}
