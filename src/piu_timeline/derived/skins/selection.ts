/** Skin identity uses independent image matches, without asserting note roles or chart timing. */
import type {RecordData} from '../types.ts';
export const format={schema:1,minimum_windows:3,minimum_frames:4,minimum_directions:3,minimum_caps:12,minimum_quality:0};
export function policy(){return {...format,method:'unique_independent_cap_support',cap_identity:'source_pts_lane_position'};}
export function choose(candidates:RecordData[],requirements:RecordData=policy()):RecordData{
 if(requirements.schema!==1||requirements.method!=='unique_independent_cap_support'||requirements.cap_identity!=='source_pts_lane_position'||
  ['minimum_windows','minimum_frames','minimum_directions','minimum_caps'].some(k=>!Number.isInteger(requirements[k])||requirements[k]<1)||
  !Number.isFinite(requirements.minimum_quality)||requirements.minimum_quality<0||requirements.minimum_quality>1)throw Error('Invalid skin selection requirements');
 const evidence=candidates.map(candidate=>{
  if(!Array.isArray(candidate.observations)||candidate.observations.some(o=>!Number.isInteger(o.window)||o.window<0||
   !Number.isFinite(o.source_pts_seconds)||!Number.isInteger(o.lane)||o.lane<0||!Number.isFinite(o.y)||!Number.isFinite(o.quality)))throw new Error('Invalid skin sample observations');
  const eligible=candidate.observations.filter(o=>o.method==='skin_image'&&['tap','hold_start','hold_end'].includes(o.template_role)&&o.quality>=requirements.minimum_quality);
  const caps=[...new Map(eligible.map(o=>[`${o.source_pts_seconds}:${o.lane}:${o.y}`,o])).values()];
  const windows=[...new Set(caps.map(o=>o.window))],frames=[...new Set(caps.map(o=>o.source_pts_seconds))],directions=[...new Set(caps.map(o=>o.lane%5))];
  const qualified=windows.length>=requirements.minimum_windows&&frames.length>=requirements.minimum_frames&&directions.length>=requirements.minimum_directions&&caps.length>=requirements.minimum_caps;
  return {selection:candidate.selection,qualified,windows,frames,directions,caps:caps.length,
   full_patterns:caps.filter(o=>o.classification_status==='full_pattern').length};
 });
 const qualified=evidence.filter(e=>e.qualified);
 if(qualified.length!==1)return {status:'unresolved',reason:qualified.length?'ambiguous_skin_images':'insufficient_skin_image_support',evidence};
 return {status:'selected',selection:qualified[0].selection,evidence};
}
