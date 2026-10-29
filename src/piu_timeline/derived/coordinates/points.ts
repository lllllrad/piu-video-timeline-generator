/** Named views of stored trajectories; selecting a view never converts a coordinate. */
import type {Interval} from '../types.ts';
interface StoredPoints {points?:Interval[]; detected_points?:Interval[]; head_registration?:{coordinate_method?:string; coordinate_status?:string}}
export interface Trajectory<Purpose extends 'detection'|'fit'> {
  readonly purpose:Purpose;
  readonly frame:'analysis_image_pixels';
  readonly vertical_axis:'down';
  readonly points:ReadonlyArray<Readonly<Interval>>;
}
/** Image ownership, cap/body connectivity, masks and occlusion use original anchors. */
export function detectionTrajectory(note:StoredPoints):Trajectory<'detection'>{
  const registration=note.head_registration;
  if(note.detected_points==null&&(registration?.coordinate_status==='projected'||
    ['native_cap_measurements','native_image_anchors'].includes(registration?.coordinate_method)))
    throw new Error('Projected fit trajectory is missing original detected_points');
  return {purpose:'detection',frame:'analysis_image_pixels',vertical_axis:'down',points:note.detected_points??note.points??[]};
}
/** Motion and beat fits use the producer's trajectory, qualified separately by its basis. */
export function fitTrajectory(note:StoredPoints):Trajectory<'fit'>{
  return {purpose:'fit',frame:'analysis_image_pixels',vertical_axis:'down',points:note.points??[]};
}
