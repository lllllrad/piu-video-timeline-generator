/** Revalidate native gap failures with acquired endpoint measurement bounds. */
import {contracts} from './contracts.ts';
import {equal} from './math.ts';
import type {RecordData} from './types.ts';
const F=contracts.native_gap_validation,A=contracts.native_anchor,EPS=1e-8;

export class NativeGapMeasurements {
  data:RecordData;
  records:Map<number,RecordData>;
  timeline:Map<number,number>;
  observations=new Map<number,Map<number,RecordData>>();
  points=new Map<number,Map<number,number>>();
  constructor(data:RecordData){
    this.data=data;this.records=new Map((data.head_registration?.notes??[]).map(r=>[r.note,r]));
    this.timeline=new Map((data.scroll_motion?.samples??[]).map(s=>[s.time,s.source_pts]));
  }
  compare(w:RecordData):RecordData{
    const failed=reason=>({status:'unresolved',reason,peer_notes:w.peer_notes});
    if(w.independent_coordinate_models?.length)return failed('independent_coordinate_conflict');
    if(!Array.isArray(w.peer_notes)||w.peer_notes.length!==2||!Number.isFinite(w.reconstructed_gap_pixels))return failed('unsupported_gap_comparison');
    const predictionError=w.prediction_uncertainty_pixels??0;
    if(!Number.isFinite(predictionError)||predictionError<0)return failed('invalid_prediction_uncertainty');
    const [a,b]=w.peer_notes,registration=this.data.head_registration;
    if(a===b)return failed('duplicate_peer_identity');
    if(!equal(registration?.format?.native_cap_registration,A))return failed('unsupported_registration_contract');
    const records=w.peer_notes.map(i=>this.records.get(i));
    if(records.some(r=>r?.coordinate_method!=='native_image_anchors'))return failed('missing_image_coordinates');
    if(records.some(r=>new Set(r.observations.map(o=>o.time)).size!==r.observations.length))return failed('duplicate_measurement_time');
    const measurements=w.peer_notes.map(i=>{if(!this.observations.has(i))this.observations.set(i,new Map(this.records.get(i).observations.map(o=>[o.time,o])));return this.observations.get(i);});
    if(!this.points.has(b))this.points.set(b,new Map(this.data.notes[b].points));
    const second=this.points.get(b),timeline=this.timeline;
    const points=this.data.notes[a].points.filter(([t])=>second.has(t)&&w.visible_start_seconds<=t&&t<=w.visible_end_seconds);
    if(points.length<F.minimum_frames||points.at(-1)[0]-points[0][0]<F.minimum_span_seconds)return failed('insufficient_coobserved_positions');
    let lo=-Infinity,hi=Infinity;const samples=[];
    for(const [time,y]of points){
      const positions=[y,second.get(time)],observed=measurements.map(m=>m.get(time)),errors=[];
      for(const [i,o]of observed.entries()){
        if(!o||o.native_cap_registration_status==='conflicting'||!o.template||!Number.isFinite(o.native_y_pixels)||Math.abs(o.native_y_pixels-positions[i])>EPS)
          return failed('unqualified_native_position');
        const e=o.native_cap_coordinate_uncertainty_pixels,scale=o.native_cap_reference_scale_y;
        if(![e,scale].every(v=>typeof v==='number'&&Number.isFinite(v)&&v>0)||Math.abs(e-A.coordinate_uncertainty_pixels*scale)>EPS)
          return failed('unqualified_position_uncertainty');
        if(!Number.isFinite(o.source_pts_seconds)||!Number.isFinite(timeline.get(time))||Math.abs(o.source_pts_seconds-timeline.get(time))>1e-6)
          return failed('source_pts_conflict');
        errors.push(e);
      }
      const gap=positions[1]-positions[0],error=errors[0]+errors[1];
      lo=Math.max(lo,gap-error);hi=Math.min(hi,gap+error);
      samples.push({time,source_pts_seconds:timeline.get(time),positions_pixels:positions,coordinate_uncertainties_pixels:errors,gap_pixels:gap});
    }
    if(new Set(samples.map(s=>s.source_pts_seconds)).size!==samples.length)return failed('duplicate_source_pts');
    const predicted=w.reconstructed_gap_pixels,predictionRange=[predicted-predictionError,predicted+predictionError];
    return {status:lo<=hi+EPS&&lo-EPS<=predictionRange[1]&&predictionRange[0]<=hi+EPS?'explained':'unresolved',
      reason:'declared_native_endpoint_errors',peer_notes:w.peer_notes,reconstructed_gap_pixels:predicted,
      allowed_gap_range_pixels:[lo,hi],prediction_range_pixels:predictionRange,prediction_uncertainty_pixels:predictionError,samples};
  }
}

/** Only acquisition fields needed to validate physical endpoint intervals. */
export function measurementInput(registration:RecordData):RecordData{
  const keys=['time','source_pts_seconds','native_y_pixels','template','native_cap_registration_status',
    'native_cap_coordinate_uncertainty_pixels','native_cap_reference_scale_y'];
  return {format:{native_cap_registration:registration.format?.native_cap_registration},
    notes:(registration.notes??[]).map(r=>({note:r.note,coordinate_method:r.coordinate_method,
      observations:r.observations.map(o=>Object.fromEntries(keys.filter(k=>Object.hasOwn(o,k)).map(k=>[k,o[k]])))}))};
}

export function resolve(data: RecordData): RecordData {
  const original=data.timing_reconstruction,warnings:RecordData[]=original?.warnings??[];
  const eligible=warnings.flatMap((w,i)=>w.reason==='shared_spacing_reconstruction_conflict'?[i]:[]);
  if(!eligible.length)return {};
  const measuredGaps=new NativeGapMeasurements(data);
  const comparisons=new Map(eligible.map(i=>[i,measuredGaps.compare(warnings[i])])),restored=[],attempts=[],notes=data.notes.map(n=>({...n}));
  for(const [i,n]of notes.entries()){
    if(n.status!=='excluded'||n.reason!=='shared_spacing_reconstruction_conflict'||n.timing_reconstruction?.reason!==n.reason)continue;
    const own=warnings.flatMap((w,j)=>w.note===i?[j]:[]);
    if(!own.length||own.some(j=>comparisons.get(j)?.status!=='explained')){
      attempts.push({note:i,status:'unresolved',reason:'native_checks_unresolved',warnings:own});continue;
    }
    const previous=n.timing_reconstruction.unaccepted_previous_estimate,c=n.motion_clock,phase=n.clock_target_phase??n.motion_target_phase;
    if(!previous||!c||![previous.target_seconds,previous.prediction_uncertainty_seconds,c.origin,c.velocity,c.intercept,phase].every(Number.isFinite)||
      c.velocity<=0||previous.prediction_uncertainty_seconds<0||Math.abs(c.origin+(phase-c.intercept)/c.velocity-previous.target_seconds)>1e-8){
      attempts.push({note:i,status:'unresolved',reason:'source_clock_unavailable_or_stale',warnings:own});continue;
    }
    const measured=Math.max(...own.flatMap(j=>comparisons.get(j).samples.map(s=>s.coordinate_uncertainties_pixels[warnings[j].peer_notes.indexOf(i)])));
    const oldError=Math.max(contracts.local_clock.position_floor_pixels,2*(n.residual_pixels??0),n.head_registration?.coordinate_uncertainty_pixels??0);
    if(!Number.isFinite(oldError)){attempts.push({note:i,status:'unresolved',reason:'invalid_source_uncertainty',warnings:own});continue;}
    const extra=Math.max(0,measured-oldError)/c.velocity,source=n.timing_reconstruction;
    Object.assign(n,{...previous,status:'estimated',reason:null,prediction_uncertainty_seconds:previous.prediction_uncertainty_seconds+extra,
      timing_reconstruction:{status:'restored',format:original.format,method:'native_image_gap_validation',previous_motion_attempt:source,
        native_gap_comparisons:own,additional_coordinate_uncertainty_seconds:extra}});
    restored.push(i);
    attempts.push({note:i,status:'restored',warnings:own});
  }
  if(!restored.length&&original.native_gap_validation)return {};
  const remaining=warnings.filter(w=>!restored.includes(w.note));
  return {notes,timing_reconstruction:{...original,warnings:remaining,status:remaining.length?'failed':'restored',
    restored_notes:(original.restored_notes??0)+restored.length,failed_notes:new Set(remaining.map(w=>w.note)).size,
    native_gap_validation:{format:F,source_warnings:warnings,comparisons:[...comparisons].map(([warning,proof])=>({warning,...proof})),attempts,restored_notes:restored}}};
}
