/** Independent RGB windows; immutable inputs and original native clocks. */
import {recognizePlay} from './play_search.ts';
import {compare,patch,reason,policy,stages,changeCandidates} from './model.ts';
import {regions} from './regions.ts';
function perFrame(capture,event,fit,reference) {
 return event.frames.map(frame=>{
  const query=patch(capture,frame,fit?.dx??0,fit?.dy??0),failure=reason(query);
  const candidates=[];
  if(!failure&&reference)for(let i=0;i<reference.patches.length;i++) {
   const ref=reference.patches[i];if(!ref||reason(ref))continue;
   const cleaned=regions(query,ref),error=compare(cleaned.patch,ref),raw=compare(query,ref);
   if(error!==null&&raw!==null)candidates.push({stage:i,reference_relative_seconds:stages[i],error,raw_error:raw,
    visible_pixels:cleaned.patch.visible.reduce((a,b)=>a+b,0),image_outlier_regions:cleaned.removed});
  }
  candidates.sort((a,b)=>a.error-b.error);const best=candidates[0];
  return {event:event.id,lane:event.lane,playback_seconds:frame.time,source_pts_seconds:frame.pts,
   origin_pixels:[frame.crop[0]+23+(fit?.dx??0),frame.crop[1]+23+(fit?.dy??0)],
   position_basis:'receptor_prior_plus_sequence_RGB_translation',source_crop:frame.crop,
   status:failure??(!best?'no_visible_reference':best.error>policy.maxError||best.raw_error>policy.maxRawError?'no_image_correspondence':'appearance_candidate'),
   reference:reference?.id??null,candidates:best?candidates.filter(c=>c.error<=best.error+.015):[],
   phase_units:'reference_marker_relative_seconds_not_calibrated_effect_age'};
 });
}
export function measure(capture,bank,event) {
   const windowCapture={...capture,events:[event]};
   const refs=bank.byKind.get(event.kind)??[],result=refs.length?recognizePlay(windowCapture,event,refs):{status:'unbound_direction',best:null,order_margin:null,alternatives:[]};
   const fit=result.best?.fit,ref=refs.find(r=>r.id===result.best?.reference);
   const witnessed=fit?.patches.filter(p=>p&&!reason(p)).map(p=>p.frame)??event.frames;
   const range=witnessed.length?[Math.min(...witnessed.map(f=>f.time)),Math.max(...witnessed.map(f=>f.time))]:[event.marker,event.marker];
   const observation=({id:event.id,lane:event.lane,kind:event.kind,selection_kind:('selection_kind'in event?event.selection_kind:null),reference_source_overlap:event.frames.some(f=>bank.trainingFrames.get(event.kind)?.has(f.pts)),status:result.status,
    observation_range:range,marker_seconds:event.marker,alignment_offset:fit?.offset??null,translation:fit?[fit.dx,fit.dy]:null,
    error:fit?.error??null,raw_error:fit?.rawError??null,reference:result.best?.reference??null,
    order_margin:result.order_margin??null,reference_alternatives:result.alternatives??[],temporal_alternatives:fit?.alternatives??[],
    image_change_candidates:changeCandidates(windowCapture,event),physical_input_range:null});
   return {event:observation,rows:perFrame(windowCapture,event,fit,ref)};
}
