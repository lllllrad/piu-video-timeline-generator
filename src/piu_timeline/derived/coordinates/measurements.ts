/** The only adapter from image-registration wire fields to coordinate evidence. */
import {contracts} from '../contracts.ts';
import {equal} from '../math.ts';
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
  | (Position & {kind:'conflicting_center_projection'; uncertaintyPixels:number})
  | (Position & {kind:'image_reference_anchor'})
  | {kind:'unavailable'; reason:string};

export function sameBasis(a:CoordinateBasis,b:CoordinateBasis):boolean{
  return a.kind!=='unavailable'&&b.kind!=='unavailable'&&equal(a,b);
}

export function imagePosition(sample:RecordData|undefined, trajectoryY:number, registrationFormat:RecordData):ImagePosition{
  const unavailable=(reason:string):ImagePosition=>({kind:'unavailable',reason});
  if(!sample||!sample.template||![sample.time,sample.source_pts_seconds,sample.native_y_pixels,trajectoryY].every(Number.isFinite)||
    Math.abs(sample.native_y_pixels-trajectoryY)>1e-8)return unavailable('unqualified_native_position');
  const reference:ReferenceIdentity=sample.cap_reference_sha256?{kind:'sha256',value:sample.cap_reference_sha256}:{kind:'template',value:sample.template};
  const position:Position={frame:'analysis_image_pixels',recordingSeconds:sample.time,sourcePtsSeconds:sample.source_pts_seconds,
    yPixels:trajectoryY,reference};
  const error=sample.native_cap_coordinate_uncertainty_pixels,scale=sample.native_cap_reference_scale_y;
  const contract=equal(registrationFormat?.native_cap_registration,contracts.native_anchor);
  const validScale=typeof scale==='number'&&Number.isFinite(scale)&&scale>0;
  const nativeBound=validScale?scale*contracts.native_anchor.coordinate_uncertainty_pixels:NaN;
  if(sample.native_cap_registration_status==='conflicting'){
    const projection=sample.native_cap_projection_uncertainty_pixels;
    if(!contract||!validScale||typeof projection!=='number'||!Number.isFinite(projection)||projection<nativeBound||!sample.native_cap_reference_template)
      return unavailable('unqualified_conflicting_projection');
    return {...position,kind:'conflicting_center_projection',uncertaintyPixels:projection};
  }
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
