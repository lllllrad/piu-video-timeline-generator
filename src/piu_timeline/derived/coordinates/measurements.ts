/** The only adapter from image-registration wire fields to coordinate evidence. */
import {contracts} from '../contracts.ts';
import {equal,roundoff} from '../math.ts';
import type {RecordData} from '../types.ts';

export type ReferenceIdentity = {kind:'sha256'|'template'; value:string};
export type CoordinateBasis =
  | {kind:'native_cap_center'}
  | {kind:'image_reference_anchor'; reference:ReferenceIdentity}
  | {kind:'unavailable'; reason:string};
interface Position {
  frame:'analysis_image_pixels'; recordingSeconds:number; sourcePtsSeconds:number;
  yPixels:number; reference:ReferenceIdentity;
}
export type ImagePosition =
  | (Position & {kind:'native_cap_center'; uncertaintyPixels:number})
  | (Position & {kind:'image_reference_anchor'})
  | {kind:'unavailable'; reason:string};

export function sameBasis(a:CoordinateBasis,b:CoordinateBasis):boolean{
  return a.kind!=='unavailable'&&b.kind!=='unavailable'&&equal(a,b);
}

export function imagePosition(sample:RecordData|undefined, trajectoryY:number, registrationFormat:RecordData):ImagePosition{
  const unavailable=(reason:string):ImagePosition=>({kind:'unavailable',reason});
  if(!sample||!sample.template||![sample.time,sample.source_pts_seconds,sample.native_y_pixels,trajectoryY].every(Number.isFinite)||
    Math.abs(sample.native_y_pixels-trajectoryY)>roundoff(sample.native_y_pixels,trajectoryY))return unavailable('unqualified_native_position');
  const reference:ReferenceIdentity=sample.cap_reference_sha256?{kind:'sha256',value:sample.cap_reference_sha256}:{kind:'template',value:sample.template};
  const position:Position={frame:'analysis_image_pixels',recordingSeconds:sample.time,sourcePtsSeconds:sample.source_pts_seconds,
    yPixels:trajectoryY,reference};
  const error=sample.native_cap_coordinate_uncertainty_pixels,scale=sample.native_cap_reference_scale_y;
  const contract=equal(registrationFormat?.native_cap_registration,contracts.native_anchor);
  const validScale=typeof scale==='number'&&Number.isFinite(scale)&&scale>0;
  if(sample.native_cap_registration_status)return unavailable(sample.native_cap_registration_status);
  const localization=sample.native_cap_localization;
  if(localization){
    const rules=contracts.image_coordinates.localization, score=localization.normalized_score,runner=localization.runner_up_score,
      projection=localization.projection,pixels=localization.pixel_evidence,limit=localization.maximum_squared_rgb_error;
    if(!contract||!validScale||!equal(registrationFormat?.localization,rules)||
      localization.method!==rules.method||localization.coordinate_frame!==rules.coordinate_frame||
      !Number.isFinite(score)||score<0||score>1||error!==0||
      (sample.native_cap_sampling_uncertainty_pixels??0)!==0||sample.native_cap_projection_uncertainty_pixels!==0||
      !sample.native_cap_reference_template||
      !pixels||pixels.method!==rules.pixel_method||!Number.isInteger(pixels.compared_pixels)||pixels.compared_pixels<=0||
      !Number.isInteger(pixels.vertical_contrast_pixels)||pixels.vertical_contrast_pixels<=0||pixels.vertical_contrast_pixels>pixels.compared_pixels||
      !Number.isFinite(limit)||limit<=0||limit>.03||
      ![pixels.squared_rgb_error,pixels.vertical_contrast_error].every(v=>Number.isFinite(v)&&v>=0&&v<=limit)||
      Math.abs(pixels.squared_rgb_error/limit-score)>rules.numeric_epsilon||
      !Number.isInteger(localization.candidate_positions)||localization.candidate_positions<1||
      !projection||![projection.detected_y_pixels,projection.center_offset_y_pixels,projection.reference_scale_y].every(Number.isFinite)||
      projection.reference_scale_y!==scale||
      Math.abs(projection.detected_y_pixels+projection.center_offset_y_pixels*scale-trajectoryY)>
        roundoff(projection.detected_y_pixels,projection.center_offset_y_pixels*scale,trajectoryY)||
      (runner===null&&(localization.candidate_positions!==1||localization.score_margin!==null))||
      (runner!==null&&(!Number.isFinite(runner)||runner<score||
        !Number.isFinite(localization.score_margin)||localization.candidate_positions<2||
        Math.abs(localization.score_margin-(runner-score))>rules.numeric_epsilon||
        runner-score<=rules.minimum_normalized_score_margin)))
      return unavailable('unqualified_image_localization');
    return {...position,kind:'native_cap_center',uncertaintyPixels:0};
  }
  if(registrationFormat?.localization&&error!=null)return unavailable('missing_image_localization');
  const sampling=sample.native_cap_sampling_uncertainty_pixels??0;
  if(sampling!==0&&(!equal(registrationFormat?.position_search,contracts.image_coordinates.position_search)||
    sampling!==contracts.image_coordinates.position_search.uncertainty_pixels||!Array.isArray(sample.sampling_origin_pixels)))
    return unavailable('unqualified_search_uncertainty');
  const nativeBound=validScale?scale*contracts.native_anchor.coordinate_uncertainty_pixels+sampling:NaN;
  if(error!=null){
    if(!contract||!validScale||typeof error!=='number'||!Number.isFinite(error)||error<=0||Math.abs(error-nativeBound)>1e-9)
      return unavailable('unqualified_position_uncertainty');
    return {...position,kind:'native_cap_center',uncertaintyPixels:error};
  }
  return {...position,kind:'image_reference_anchor'};
}

/** Batched native-adapter transport; qualification is identical to direct TS use. */
export function imagePositions(requests:{sample:RecordData; trajectoryY:number}[],format:RecordData):ImagePosition[]{
  return requests.map(r=>imagePosition(r.sample,r.trajectoryY,format));
}
