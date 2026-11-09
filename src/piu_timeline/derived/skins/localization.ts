/** Locate one cap on the sampled image grid; ambiguity supplies no position. */
import {contracts} from '../contracts.ts';
import {roundoff} from '../math.ts';
import type {RecordData} from '../types.ts';

const F=contracts.image_coordinates.localization;
type Comparison={template:string;comparison_index:number;image_y:number;cap_error:number;maximum_error:number;
 scale_y:number;same_cap:boolean;center_offset_y_pixels?:number;reference?:string;shared_cap_pixels?:RecordData;localization_pixels?:RecordData};
export type Request={height:number;raw_y:number;comparisons:Comparison[]};
type Result={measurement:RecordData;conflict:RecordData|null;anchors:RecordData[]};

export function resolve(request:Request):Result{
 if(!Number.isFinite(request.height)||request.height<=0||!Number.isFinite(request.raw_y))throw Error('Invalid cap coordinate grid');
 const choices=request.comparisons.map(c=>{
  if(![c.image_y,c.cap_error,c.maximum_error,c.scale_y].every(Number.isFinite)||c.cap_error<0||c.maximum_error<=0||c.scale_y<=0)
   throw Error('Invalid cap position comparison');
  if(c.center_offset_y_pixels!=null&&!Number.isFinite(c.center_offset_y_pixels))throw Error('Invalid reference-center offset');
  const p=c.localization_pixels;
  const qualified=!!p&&p.method===F.pixel_method&&Number.isInteger(p.compared_pixels)&&p.compared_pixels>0&&
   Number.isInteger(p.vertical_contrast_pixels)&&p.vertical_contrast_pixels>0&&p.vertical_contrast_pixels<=p.compared_pixels&&
   [p.squared_rgb_error,p.vertical_contrast_error].every(Number.isFinite)&&p.squared_rgb_error>=0&&
   p.squared_rgb_error<=c.maximum_error&&p.vertical_contrast_error>=0&&p.vertical_contrast_error<=c.maximum_error;
  return {...c,qualified,detected_y_pixels:c.image_y*request.height,
   normalized_score:(Number.isFinite(p?.squared_rgb_error)?p.squared_rgb_error:c.cap_error)/c.maximum_error,
   ...(c.center_offset_y_pixels!=null?{native_y_pixels:c.image_y*request.height+c.center_offset_y_pixels*c.scale_y}:{})};
 }).filter(c=>c.same_cap&&c.cap_error<=c.maximum_error);
 const anchors=[];
 for(const reference of new Set(choices.filter(c=>c.qualified).map(c=>c.reference).filter(Boolean))){
  const samples=choices.filter(c=>c.reference===reference&&c.qualified),best=samples.reduce((a,b)=>b.normalized_score<a.normalized_score?b:a);
  const rivals=samples.filter(c=>Math.abs(c.detected_y_pixels-best.detected_y_pixels)>roundoff(c.detected_y_pixels,best.detected_y_pixels));
  if(rivals.some(c=>c.normalized_score-best.normalized_score<=F.minimum_normalized_score_margin))continue;
  anchors.push({yPixels:best.detected_y_pixels,uncertaintyPixels:0,
   basis:{kind:'image_reference_anchor',reference:{kind:'sha256',value:reference}}});
 }
 const registered=choices.filter(c=>Number.isFinite(c.native_y_pixels)&&c.qualified);
 if(!registered.length){
  const failed=choices.some(c=>Number.isFinite(c.native_y_pixels))||choices.length>0&&!choices.some(c=>c.qualified);
  return {measurement:{},conflict:failed?{reason:'image_localization_pixels_unqualified',comparisons:choices}:null,
   anchors:failed?[]:anchors};
 }
 const best=registered.reduce((a,b)=>b.normalized_score<a.normalized_score?b:a);
 const rivals=registered.filter(c=>Math.abs(c.native_y_pixels-best.native_y_pixels)>roundoff(c.native_y_pixels,best.native_y_pixels));
 const runner=rivals.length?rivals.reduce((a,b)=>b.normalized_score<a.normalized_score?b:a):null;
 const margin=runner?runner.normalized_score-best.normalized_score:null;
 const evidence={method:F.method,normalized_score:best.normalized_score,runner_up_score:runner?.normalized_score??null,
  score_margin:margin,candidate_positions:registered.reduce<number[]>((rows,c)=>
   rows.some(y=>Math.abs(y-c.native_y_pixels)<=roundoff(y,c.native_y_pixels))?rows:[...rows,c.native_y_pixels],[]).length,
  coordinate_frame:F.coordinate_frame,
  pixel_evidence:best.localization_pixels,
  maximum_squared_rgb_error:best.maximum_error,
  projection:{detected_y_pixels:best.detected_y_pixels,center_offset_y_pixels:best.center_offset_y_pixels,reference_scale_y:best.scale_y}};
 if(runner&&margin<=F.minimum_normalized_score_margin)
  return {measurement:{},conflict:{reason:'image_position_ambiguous',localization:evidence,comparisons:registered},anchors:[]};
 return {measurement:{native_y_pixels:best.native_y_pixels,native_cap_coordinate_uncertainty_pixels:0,
  native_cap_projection_uncertainty_pixels:0,native_cap_reference_scale_y:best.scale_y,
  native_cap_reference_template:best.template,native_cap_reference_error:best.cap_error,
  native_cap_comparison_index:best.comparison_index,native_cap_localization:evidence,
  ...(best.shared_cap_pixels?{native_cap_shared_pixel_evidence:best.shared_cap_pixels}:{})},conflict:null,anchors};
}

export function resolveMany(requests:Request[]){return requests.map(resolve);}
