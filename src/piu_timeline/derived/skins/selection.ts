/** Skin identity uses independent image matches, without asserting note roles or chart timing. */
import type {RecordData} from '../types.ts';
export const format={schema:1,minimum_windows:3,minimum_frames:4,minimum_directions:3,minimum_caps:12,minimum_quality:.5};
export function policy(){return {...format,method:'unique_independent_cap_support',cap_identity:'source_pts_lane_position'};}
export function choose(candidates:RecordData[]):RecordData{
 const evidence=candidates.map(candidate=>{
  if(!Array.isArray(candidate.observations)||candidate.observations.some(o=>!Number.isInteger(o.window)||o.window<0||
   !Number.isFinite(o.source_pts_seconds)||!Number.isInteger(o.lane)||o.lane<0||!Number.isFinite(o.y)||!Number.isFinite(o.quality)))throw new Error('Invalid skin sample observations');
  const eligible=candidate.observations.filter(o=>o.method==='skin_image'&&o.template_role!=='hold_body'&&o.quality>=format.minimum_quality);
  const caps=[...new Map(eligible.map(o=>[`${o.source_pts_seconds}:${o.lane}:${o.y}`,o])).values()];
  const windows=[...new Set(caps.map(o=>o.window))],frames=[...new Set(caps.map(o=>o.source_pts_seconds))],directions=[...new Set(caps.map(o=>o.lane%5))];
  const qualified=windows.length>=format.minimum_windows&&frames.length>=format.minimum_frames&&directions.length>=format.minimum_directions&&caps.length>=format.minimum_caps;
  return {selection:candidate.selection,qualified,windows,frames,directions,caps:caps.length,
   full_patterns:caps.filter(o=>o.classification_status==='full_pattern').length};
 });
 const qualified=evidence.filter(e=>e.qualified);
 if(qualified.length!==1)return {status:'unresolved',reason:qualified.length?'ambiguous_skin_images':'insufficient_skin_image_support',evidence};
 return {status:'selected',selection:qualified[0].selection,evidence};
}
